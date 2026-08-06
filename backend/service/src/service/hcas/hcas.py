from __future__ import annotations

# Standard library imports
from datetime import UTC, date, datetime
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from sqlalchemy.exc import IntegrityError

# First-party imports
from models.auth.user import User
from models.enums import AccountOrigin, ContractType, HcaApplicationStatus, UserRole
from models.geo.postal_address import PostalAddress
from models.people.availability_slot import AvailabilitySlot
from models.people.certification import Certification
from models.people.driving_license import DrivingLicense
from models.people.hca import Hca
from models.people.hca_application import HcaApplication
from service.auth.auth import AuthService
from service.companies.exceptions import (
    MTCompanyNotAcceptingApplications,
    MTCompanyNotFound,
)
from service.hcas.exceptions import (
    MTApplicationAlreadyDecided,
    MTApplicationForbidden,
    MTApplicationNotFound,
    MTAvailabilitySlotNotFound,
    MTDuplicateApplication,
    MTHcaForbidden,
    MTHcaHasAccount,
    MTHcaNotFound,
)
from storage.repositories.company import CompanyRepository
from storage.repositories.hca import HcaRepository
from storage.repositories.hca_application import HcaApplicationRepository
from storage.repositories.user import UserRepository
from storage.s3.exceptions import MTS3DeleteFailed
from storage.s3.s3_storage import S3Storage


class HcaService:
    """Everything the application does with a Home Care Assistant.

    Attributes:
        hcas (HcaRepository): The assistant store.
        photos (Optional[S3Storage]): The object store holding the
            photographs.
        applications (Optional[HcaApplicationRepository]): The application
            store.
        companies (Optional[CompanyRepository]): The company store.
        users (Optional[UserRepository]): The account store.
        auth (Optional[AuthService]): Hashes an applicant's chosen password.
        logger (Logger): Logger for assistant operations.

    Notes:
       - The photograph lives in an object store and the record holds its URL,
         but that is one entity with two homes, not two entities. Keeping both
         halves here means the ordering rule below is stated once, in the place
         that owns the record, rather than split across services that each know
         only half of it.
       - Two mutations are deliberately narrow. :meth:`set_employment` is all a
         manager may change, and :meth:`add_availability` is how an absence is
         filed. A single general update would let either caller overwrite fields
         they have no business touching.
    """

    def __init__(
        self,
        hcas: HcaRepository,
        photos: Optional[S3Storage] = None,
        applications: Optional[HcaApplicationRepository] = None,
        companies: Optional[CompanyRepository] = None,
        users: Optional[UserRepository] = None,
        auth: Optional[AuthService] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            hcas (HcaRepository): The assistant store.
            photos (Optional[S3Storage]): The object store holding the
                photographs, needed only by the photograph methods.
            applications (Optional[HcaApplicationRepository]): The application
                store, needed only by the recruitment methods.
            companies (Optional[CompanyRepository]): The company store, same.
            users (Optional[UserRepository]): The account store, same.
            auth (Optional[AuthService]): Hashes the password an applicant
                chose. Hashing lives on the account service now that it owns
                the credential rules.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.hcas = hcas
        self.photos = photos
        self.applications = applications
        self.companies = companies
        self.users = users
        self.auth = auth
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("HcaService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _remove_superseded(
        self, previous_url: Optional[str], current_url: Optional[str]
    ) -> None:
        """Delete a photograph that is no longer referenced, best effort.

        Args:
            previous_url (Optional[str]): The URL stored before.
            current_url (Optional[str]): The URL stored now, so an unchanged
                one is never deleted.

        Notes:
            Failures are logged, never raised. By the time this runs the record
            is already correct, so raising would report a failure for an
            operation that succeeded. The cost is an orphaned object, which is
            a housekeeping problem rather than a correctness one.
        """
        if not previous_url or previous_url == current_url:
            return
        try:
            await self.photos.delete_photo(previous_url)
        except MTS3DeleteFailed as exc:
            self.logger.warning(
                "Could not remove the superseded photograph %s: %s. The object "
                "is orphaned but the record is correct.",
                previous_url,
                exc,
            )

    def _check_owns(self, hca_id: str, caller: User) -> None:
        """Refuse a caller acting on an assistant who is not them.

        Args:
            hca_id (str): The assistant being acted on.
            caller (User): Who is asking.

        Raises:
            MTHcaForbidden: If an assistant addresses a colleague.

        Notes:
            - **The comparison can only be made here.** A route guard proves the
              caller holds the assistant role; nothing at the routing layer stops
              assistant A putting assistant B's identifier in the path, and an
              absence filed against a colleague would take them off the rota.
            - Managers and administrators pass: filing an absence for somebody
              who telephoned in sick is exactly their job.
        """
        if caller.is_manager():
            return
        if not caller.owns_hca(hca_id):
            self.logger.warning(
                "Account %s attempted to act on assistant %s.",
                caller.email,
                hca_id,
            )
            raise MTHcaForbidden(
                f"You may only manage your own availability, not that of "
                f"assistant {hca_id!r}."
            )

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, hca: Hca) -> Hca:
        """Register an assistant.

        Args:
            hca (Hca): The assistant to register.

        Returns:
            Hca: The stored assistant.

        Notes:
            The home address geocodes as the model is built, so an assistant
            whose address the map does not know is still registered — with a
            ``geocoding_error`` recorded. They simply cannot be routed until
            the address resolves, which the planner reports as an unassignable
            requirement rather than a failed registration.
        """
        self.logger.info("Registering assistant %s.", hca.full_name())
        stored = await self.hcas.create(hca)
        if not stored.address.is_geocoded():
            self.logger.warning(
                "Assistant %s has an unresolved address (%s); they cannot be "
                "routed until it geocodes.",
                stored.id,
                stored.address.geocoding_error,
            )
        return stored

    async def get(self, hca_id: str) -> Hca:
        """Return an assistant by identifier.

        Args:
            hca_id (str): The identifier to look up.

        Returns:
            Hca: The assistant.

        Raises:
            MTHcaNotFound: If no such assistant exists.
        """
        found = await self.hcas.get(hca_id)
        if found is None:
            self.logger.warning("Assistant %s does not exist.", hca_id)
            raise MTHcaNotFound(f"No assistant {hca_id!r} exists.")
        return found

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        search: Optional[str] = None,
        contract_type: Optional[ContractType] = None,
    ) -> List[Hca]:
        """Return a page of assistants.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            search (Optional[str]): Case-insensitive fragment.
            contract_type (Optional[ContractType]): Restrict to one contract.

        Returns:
            List[Hca]: The matching assistants.
        """
        self.logger.debug("Listing assistants: page=%d search=%r.", page, search)
        return await self.hcas.list(
            page=page, size=size, search=search, contract_type=contract_type
        )

    async def set_employment(
        self,
        hca_id: str,
        contract_type: ContractType,
        certifications: List[Certification],
    ) -> Hca:
        """Change an assistant's contract type and qualifications.

        Args:
            hca_id (str): The assistant to change.
            contract_type (ContractType): The new employment contract.
            certifications (List[Certification]): The qualifications now held.

        Returns:
            Hca: The updated assistant.

        Raises:
            MTHcaNotFound: If no such assistant exists.

        Notes:
            These are the only two fields a manager may change, which is
            enforced by this method existing instead of a general update — no
            manager-facing route can reach the contact details, the home
            address or the availability.
        """
        updated = await self.hcas.set_employment(hca_id, contract_type, certifications)
        if updated is None:
            raise MTHcaNotFound(f"No assistant {hca_id!r} exists.")
        self.logger.info(
            "Assistant %s is now on a %s contract with %d certification(s).",
            hca_id,
            contract_type.value,
            len(certifications),
        )
        return updated

    async def add_availability(
        self, hca_id: str, slot: AvailabilitySlot, caller: User
    ) -> AvailabilitySlot:
        """File an absence for an assistant.

        Args:
            hca_id (str): The assistant the absence belongs to.
            slot (AvailabilitySlot): The absence to record.
            caller (User): Who is filing it.

        Returns:
            AvailabilitySlot: The stored absence.

        Raises:
            MTHcaForbidden: If an assistant files against a colleague.
            MTHcaNotFound: If no such assistant exists.

        Notes:
            The owning assistant comes from the argument, never the payload, so
            an assistant cannot book a colleague off work by naming them in the
            body — and :meth:`_check_owns` stops them addressing one either.
        """
        self._check_owns(hca_id, caller)
        stored = await self.hcas.add_availability(hca_id, slot)
        if stored is None:
            raise MTHcaNotFound(f"No assistant {hca_id!r} exists.")
        self.logger.info(
            "Filed %s for assistant %s from %s to %s.",
            stored.kind.value,
            hca_id,
            stored.start_date,
            stored.end_date,
        )
        return stored

    async def remove_availability(
        self, hca_id: str, slot_id: str, caller: User
    ) -> None:
        """Withdraw a filed absence.

        Args:
            hca_id (str): The assistant the absence belongs to.
            slot_id (str): The absence to withdraw.
            caller (User): Who is withdrawing it.

        Raises:
            MTHcaForbidden: If an assistant withdraws a colleague's absence.
            MTAvailabilitySlotNotFound: If the absence does not belong to that
                assistant.

        Notes:
            The assistant is part of the lookup, so knowing a slot identifier
            is not enough to withdraw a colleague's absence — and the ownership
            check refuses before the lookup is even attempted.
        """
        self._check_owns(hca_id, caller)
        if not await self.hcas.remove_availability(hca_id, slot_id):
            self.logger.warning(
                "Absence %s does not belong to assistant %s.", slot_id, hca_id
            )
            raise MTAvailabilitySlotNotFound(
                f"No absence {slot_id!r} belongs to assistant {hca_id!r}."
            )
        self.logger.info("Withdrew absence %s for assistant %s.", slot_id, hca_id)

    async def list_availability(
        self,
        hca_id: str,
        caller: User,
        start: Optional[date] = None,
        end: Optional[date] = None,  # noqa: E501
    ) -> List[AvailabilitySlot]:
        """Return an assistant's absences within a window.

        Args:
            hca_id (str): The assistant to read.
            caller (User): Who is asking.
            start (Optional[date]): Earliest day of interest.
            end (Optional[date]): Latest day of interest.

        Returns:
            List[AvailabilitySlot]: The matching absences.

        Raises:
            MTHcaForbidden: If an assistant reads a colleague's absences.

        Notes:
            An absence carries a reason — sick leave, training — so reading a
            colleague's is a disclosure, not merely a scheduling detail.
        """
        self._check_owns(hca_id, caller)
        self.logger.debug(
            "Listing absences for assistant %s between %s and %s.",
            hca_id,
            start,
            end,
        )
        return await self.hcas.list_availability(hca_id, start=start, end=end)

    async def update_profile(
        self,
        hca_id: str,
        first_name: str,
        last_name: str,
        phone_number: str,
        email: str,
        address: PostalAddress,
        driving_license: Optional[DrivingLicense] = None,
    ) -> Hca:
        """Change an assistant's own contact details, address and licence.

        Args:
            hca_id (str): The assistant being updated.
            first_name (str): Given name.
            last_name (str): Family name.
            phone_number (str): Contact telephone number.
            email (str): Contact email address.
            address (PostalAddress): Home address.
            driving_license (Optional[DrivingLicense]): Driving licence, or
                ``None`` when the assistant holds none.

        Returns:
            Hca: The updated assistant.

        Raises:
            MTHcaNotFound: If no such assistant exists.

        Notes:
            The stored record is read first and the five editable fields are
            copied onto it, rather than a new assistant being built from the
            payload. That is what preserves the contract type, the
            certifications, the driving licence, the photograph and the declared
            absences — none of which appear in the request, and all of which
            would be silently cleared by a wholesale replacement.
        """
        existing = await self.get(hca_id)
        self.logger.info("Updating the contact details of assistant %s.", hca_id)
        updated = await self.hcas.update(
            existing.model_copy(
                update={
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone_number": phone_number,
                    "email": email,
                    "address": address,
                    "driving_license": driving_license,
                }
            )
        )
        if updated is None:
            raise MTHcaNotFound(f"No assistant {hca_id!r} exists.")
        if address.geocoding_error:
            self.logger.warning(
                "Assistant %s saved an address that did not resolve (%s); they "
                "cannot be routed until it does.",
                hca_id,
                address.geocoding_error,
            )
        return updated

    async def set_photo(self, hca_id: str, payload: bytes) -> Hca:
        """Store an assistant's photograph and attach it to their record.

        Args:
            hca_id (str): The assistant the photograph belongs to.
            payload (bytes): The image bytes.

        Returns:
            Hca: The updated assistant.

        Raises:
            MTHcaNotFound: If no such assistant exists.
            MTS3EmptyPayload: If the upload carries no bytes.
            MTS3UnsupportedContentType: If it is not an accepted image.
            MTS3PayloadTooLarge: If it exceeds the configured size.
            MTS3BucketUnavailable: If the object store cannot be reached.
            MTS3UploadFailed: If the object could not be written.

        Notes:
            The object is written **before** the record is updated. The reverse
            order would leave a record pointing at an object that does not
            exist yet, so a failure between the two steps would show a broken
            image rather than the previous one.
        """
        assistant = await self.get(hca_id)
        previous_url = (
            str(assistant.photo_url) if assistant.photo_url is not None else None
        )
        self.logger.info(
            "Storing a %d-byte photograph for assistant %s.", len(payload), hca_id
        )
        photo_url = await self.photos.upload_photo(hca_id, payload)
        updated = await self.hcas.set_photo_url(hca_id, photo_url)
        if updated is None:
            self.logger.error(
                "Assistant %s vanished while its photograph was uploading; the "
                "object at %s is now orphaned.",
                hca_id,
                photo_url,
            )
            raise MTHcaNotFound(f"No assistant {hca_id!r} exists.")
        await self._remove_superseded(previous_url, photo_url)
        self.logger.info("Assistant %s now shows %s.", hca_id, photo_url)
        return updated

    async def clear_photo(self, hca_id: str) -> Hca:
        """Remove an assistant's photograph.

        Args:
            hca_id (str): The assistant to clear.

        Returns:
            Hca: The updated assistant.

        Raises:
            MTHcaNotFound: If no such assistant exists.

        Notes:
            The link is cleared first, the opposite of the upload order. What
            matters in both cases is that the record never points at a missing
            object: on upload the object must exist first, on removal the link
            must go first.
        """
        assistant = await self.get(hca_id)
        previous_url = (
            str(assistant.photo_url) if assistant.photo_url is not None else None
        )
        updated = await self.hcas.set_photo_url(hca_id, None)
        if updated is None:
            raise MTHcaNotFound(f"No assistant {hca_id!r} exists.")
        await self._remove_superseded(previous_url, None)
        self.logger.info("Assistant %s no longer has a photograph.", hca_id)
        return updated

    async def delete(self, hca_id: str) -> None:
        """Remove an assistant and their photograph.

        Args:
            hca_id (str): The assistant to remove.

        Raises:
            MTHcaNotFound: If no such assistant exists.
            MTHcaHasAccount: If a sign-in account still points at the assistant.
        """
        assistant = await self.get(hca_id)
        previous_url = (
            str(assistant.photo_url) if assistant.photo_url is not None else None  # noqa: E501
        )
        try:
            removed = await self.hcas.delete(hca_id)
        except IntegrityError as exc:
            self.logger.warning(
                "Refused to remove assistant %s: an account still points at it.",
                hca_id,
            )
            raise MTHcaHasAccount(
                f"Assistant {hca_id!r} still has a sign-in account. Remove the "
                f"account first."
            ) from exc
        if not removed:
            raise MTHcaNotFound(f"No assistant {hca_id!r} exists.")
        await self._remove_superseded(previous_url, None)
        self.logger.info("Removed assistant %s.", hca_id)

    async def _get_application(self, application_id: str) -> HcaApplication:
        """Return an application or report that it does not exist.

        Args:
            application_id (str): The application to read.

        Returns:
            HcaApplication: The application.

        Raises:
            MTApplicationNotFound: If no such application exists.
        """
        application = await self.applications.get(application_id)
        if application is None:
            self.logger.warning("Application %s does not exist.", application_id)
            raise MTApplicationNotFound(f"No application {application_id!r} exists.")
        return application

    def _check_may_decide(self, application: HcaApplication, decider: User) -> None:
        """Refuse a decider acting on another company's queue.

        Args:
            application (HcaApplication): The application being decided.
            decider (User): The manager or administrator deciding it.

        Raises:
            MTApplicationForbidden: If the decider belongs to a different
                company.

        Notes:
            - **Row-level, like every other rule of this shape here.** A route
              guard proves the caller is a manager; it cannot tell whether the
              application identifier in the path belongs to their agency.
            - There used to be an exemption here: an administrator belonging to
              no company was treated as system-wide, so that the first agency
              could have its first application approved before any company
              existed. Nothing needs it now — an agency and its first
              administrator are created by the same call, and ``company_id`` is
              required on every account — and while it stood it meant any
              administrator without an agency could decide every agency's
              applications. Removed rather than kept as dead code, because an
              exemption that cannot currently be reached is one a later change
              can quietly make reachable again.
        """
        if decider.company_id == application.company_id:
            return
        self.logger.warning(
            "Account %s (company %s) attempted to decide an application "
            "addressed to company %s.",
            decider.email,
            decider.company_id,
            application.company_id,
        )
        raise MTApplicationForbidden(
            "You may only decide applications addressed to your own company."
        )

    def _require_pending(self, application: HcaApplication) -> None:
        """Refuse a second decision on an already-decided application.

        Args:
            application (HcaApplication): The application being decided.

        Raises:
            MTApplicationAlreadyDecided: If it has already been decided.

        Notes:
            Approving twice would create a second assistant and a second
            account for the same person; rejecting an approved one would leave
            the account it created behind, unreferenced.
        """
        if not application.is_pending():
            self.logger.warning(
                "Application %s is already %s.",
                application.id,
                application.status.value,
            )
            raise MTApplicationAlreadyDecided(
                f"Application {application.id!r} was already "
                f"{application.status.value}."
            )

    async def submit(
        self,
        company_id: str,
        first_name: str,
        last_name: str,
        phone_number: str,
        email: str,
        password: str,
        address: PostalAddress,
        contract_type: Optional[ContractType] = None,
    ) -> HcaApplication:
        """Record an assistant's own application to a company.

        Args:
            company_id (str): The company they chose.
            first_name (str): Given name.
            last_name (str): Family name.
            phone_number (str): Contact telephone number.
            email (str): The address that becomes their sign-in on approval.
            password (str): The password they chose, in plain text.
            address (PostalAddress): Where they live.
            contract_type (Optional[ContractType]): The contract applied for.

        Returns:
            HcaApplication: The pending application.

        Raises:
            MTCompanyNotFound: If the chosen company does not exist.
            MTCompanyNotAcceptingApplications: If it has closed its queue.
            MTDuplicateApplication: If they already have one outstanding with
                that company.

        Notes:
            - The password is hashed **here**, before anything is stored, and the
              plaintext is not passed on. An application can wait days for a
              decision, and a plaintext credential waiting days is one in every
              backup taken meanwhile.
            - No account is created. Until a manager approves, this person cannot
              sign in and does not appear in the users table at all.
        """
        self.logger.info(
            "Receiving an application from %s to company %s.", email, company_id
        )
        company = await self.companies.get(company_id)
        if company is None:
            self.logger.warning(
                "Refused an application from %s: company %s does not exist.",
                email,
                company_id,
            )
            raise MTCompanyNotFound(f"No company {company_id!r} exists.")
        if not company.is_accepting_applications:
            self.logger.warning(
                "Refused an application from %s: company %s is not accepting any.",
                email,
                company.name,
            )
            raise MTCompanyNotAcceptingApplications(
                f"{company.name} is not accepting applications at the moment."
            )

        existing = await self.applications.pending_for_email(email, company_id)
        if existing is not None:
            self.logger.warning(
                "Refused a second application from %s to company %s.",
                email,
                company_id,
            )
            raise MTDuplicateApplication(
                f"You already have an application pending with {company.name}."
            )

        stored = await self.applications.create(
            HcaApplication(
                company_id=company_id,
                first_name=first_name,
                last_name=last_name,
                phone_number=phone_number,
                email=email,
                address=address,
                contract_type=contract_type,
                hashed_password=self.auth.hash(password),
            )
        )
        self.logger.info(
            "Application %s from %s is awaiting a decision from company %s.",
            stored.id,
            stored.email,
            company.name,
        )
        return stored

    async def get_application(
        self, application_id: str, caller: User
    ) -> HcaApplication:
        """Return one application, if the caller's company owns it.

        Args:
            application_id (str): The application to read.
            caller (User): Who is asking.

        Returns:
            HcaApplication: The application.

        Raises:
            MTApplicationNotFound: If no such application exists.
            MTApplicationForbidden: If it belongs to another company.
        """
        application = await self._get_application(application_id)
        self._check_may_decide(application, caller)
        return application

    async def list_pending(
        self, caller: User, page: int = 1, size: Optional[int] = None
    ) -> List[HcaApplication]:
        """Return the applications awaiting the caller's company.

        Args:
            caller (User): Who is asking.
            page (int): One-based page number.
            size (Optional[int]): Page size.

        Returns:
            List[HcaApplication]: The pending applications, oldest first.

        Notes:
            Filtered by the caller's own company rather than by a parameter
            they supply. A company identifier in the query string would let a
            manager read another agency's hiring queue by changing it.
        """
        company_id = caller.company_id
        self.logger.debug("Listing pending applications for company %s.", company_id)
        applications = await self.applications.list(
            page=page,
            size=size,
            company_id=company_id,
            status=HcaApplicationStatus.PENDING,
        )
        self.logger.info(
            "%d application(s) await a decision from company %s.",
            len(applications),
            company_id,
        )
        return applications

    async def approve(
        self, application_id: str, decider: User, contract_type: ContractType
    ) -> HcaApplication:
        """Accept an application, creating the assistant and their account.

        Args:
            application_id (str): The application to approve.
            decider (User): The manager or administrator approving it.
            contract_type (ContractType): The contract they are taken on under.

        Returns:
            HcaApplication: The approved application, naming the new assistant.

        Raises:
            MTApplicationNotFound: If no such application exists.
            MTApplicationForbidden: If it belongs to another company.
            MTApplicationAlreadyDecided: If it was already decided.

        Notes:
            - The account is created with the password the applicant chose, so
              there is nothing to hand over and nothing to change at first
              sign-in — unlike the staff-created path, where an administrator
              picks the first password and the holder must replace it.
            - The contract type comes from the approver, not the application. An
              applicant may state what they are hoping for; what they are
              actually employed under is the agency's decision.
        """
        application = await self._get_application(application_id)
        self._check_may_decide(application, decider)
        self._require_pending(application)

        self.logger.info(
            "Approving application %s from %s on a %s contract.",
            application_id,
            application.email,
            contract_type.value,
        )
        assistant = await self.hcas.create(
            Hca(
                first_name=application.first_name,
                last_name=application.last_name,
                phone_number=application.phone_number,
                email=application.email,
                address=application.address,
                company_id=application.company_id,
                contract_type=contract_type,
            )
        )
        await self.users.create(
            User(
                email=application.email,
                full_name=application.full_name(),
                hashed_password=application.hashed_password,
                role=UserRole.HCA,
                hca_id=assistant.id,
                company_id=application.company_id,
                account_origin=AccountOrigin.SELF_REGISTERED,
                must_change_password=False,
            )
        )
        decided = await self.applications.update(
            application.model_copy(
                update={
                    "status": HcaApplicationStatus.APPROVED,
                    "decided_by": decider.id if decider.id else decider.email,
                    "decided_at": datetime.now(UTC),
                    "hca_id": assistant.id,
                }
            )
        )
        if decided is None:
            self.logger.error(
                "Application %s vanished between the approval and the write; "
                "the assistant and account it created are now orphaned.",
                application_id,
            )
            raise MTApplicationNotFound(f"No application {application_id!r} exists.")
        self.logger.info(
            "Application %s approved; assistant %s can now sign in.",
            application_id,
            assistant.id,
        )
        return decided

    async def reject(
        self, application_id: str, decider: User, reason: Optional[str] = None
    ) -> HcaApplication:
        """Decline an application, creating nothing.

        Args:
            application_id (str): The application to decline.
            decider (User): The manager or administrator declining it.
            reason (Optional[str]): Why, for the record.

        Returns:
            HcaApplication: The declined application.

        Raises:
            MTApplicationNotFound: If no such application exists.
            MTApplicationForbidden: If it belongs to another company.
            MTApplicationAlreadyDecided: If it was already decided.

        Notes:
            The record is kept rather than deleted, so a later application from
            the same person is recognisable as a second attempt. The chosen
            password's hash goes with it — unused, unusable, and not worth the
            extra write to clear.
        """
        application = await self._get_application(application_id)
        self._check_may_decide(application, decider)
        self._require_pending(application)

        self.logger.info("Declining application %s.", application_id)
        decided = await self.applications.update(
            application.model_copy(
                update={
                    "status": HcaApplicationStatus.REJECTED,
                    "decided_by": decider.id if decider.id else decider.email,
                    "decided_at": datetime.now(UTC),
                    "rejection_reason": reason,
                }
            )
        )
        if decided is None:
            self.logger.error(
                "Application %s vanished between the decision and the write.",
                application_id,
            )
            raise MTApplicationNotFound(f"No application {application_id!r} exists.")
        self.logger.warning(
            "Application %s from %s was declined; no account was created.",
            application_id,
            application.email,
        )
        return decided
