from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# First-party imports
from models.organisation.companies.company import Company
from models.organisation.companies.company_choice import CompanyChoice
from service.companies.exceptions import (
    MTCompanyLogoStorageUnavailable,
    MTCompanyNameTaken,
    MTCompanyNotEmpty,
    MTCompanyNotFound,
)
from storage.repositories.auth.user import UserRepository
from storage.repositories.companies.company import CompanyRepository
from storage.repositories.people.hca import HcaRepository
from storage.s3.exceptions import MTS3DeleteFailed
from storage.s3.s3_storage import S3Storage


class CompanyService:
    """Manages the agencies an assistant can apply to work for.

    Attributes:
        companies (CompanyRepository): The company store.
        logos (Optional[S3Storage]): The object store holding the logos.
        logger (Logger): Logger for company operations.

    Notes:
        - A company is **not** a tenancy boundary in this system. Customers,
          quotes and plannings are agency-wide; what a company scopes is which
          applications a manager may decide. Making it a full tenant would mean
          scoping every query in the application, which is a different piece of
          work and not what "the assistant chooses which company to register
          with" asks for.
        - **Deleting an agency is possible only while it is empty.** Every
          account and every assistant names the agency they belong to, and that
          link is now required rather than optional — so removing an agency
          somebody still points at would leave rows that cannot be rebuilt. An
          agency that has people is closed to applications rather than deleted;
          see :meth:`set_accepting_applications`. What deletion is for is the
          agency that should never have existed: one founded in error, and the
          fixtures a test campaign is obliged to remove after itself.
    """

    def __init__(
        self,
        companies: CompanyRepository,
        users: UserRepository,
        hcas: HcaRepository,
        logos: Optional[S3Storage] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            companies (CompanyRepository): The company store.
            users (UserRepository): The account store, to check an agency is
                empty before removing it.
            hcas (HcaRepository): The assistant store, for the same check.
            logos (Optional[S3Storage]): The object store holding the logos.
                Optional, because every method but the two logo ones works
                without it — and a test exercising agency deletion should not
                have to stand up an object store to do so.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.companies = companies
        self.users = users
        self.hcas = hcas
        self.logos = logos
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("CompanyService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _remove_superseded(
        self, previous_url: Optional[str], current_url: Optional[str]
    ) -> None:
        """Delete a logo that is no longer referenced, best effort.

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
        if self.logos is None or not previous_url or previous_url == current_url:
            self.logger.debug("No superseded logo to remove.")
            return
        self.logger.info("Removing the superseded logo %s.", previous_url)
        try:
            removed = await self.logos.delete_logo(previous_url)
        except MTS3DeleteFailed as exc:
            self.logger.error(
                "Could not remove the superseded logo %s: %s. The object is "
                "orphaned but the record is correct.",
                previous_url,
                exc,
            )
            return
        if not removed:
            self.logger.warning(
                "The object store declined to remove %s; it is not a logo it "
                "owns. The record is correct either way.",
                previous_url,
            )

    def _require_logo_storage(self) -> S3Storage:
        """Return the object store, refusing when the deployment has none.

        Returns:
            S3Storage: The configured store.

        Raises:
            MTCompanyLogoStorageUnavailable: If no object store was injected.

        Notes:
            Raised rather than silently skipped. A caller who uploaded an image
            and got a 2xx back would reasonably believe it was kept, and a
            record that quietly declines to hold one is worse than a route that
            says the deployment cannot.
        """
        self.logger.debug("Checking that an object store is configured.")
        if self.logos is None:
            self.logger.warning(
                "A logo operation was attempted on a deployment with no bucket."
            )
            self.logger.error(
                "No object store is configured; the logo operation cannot proceed."
            )
            raise MTCompanyLogoStorageUnavailable(
                "This deployment has no object store, so logos cannot be stored."
            )
        self.logger.info("An object store is available to hold logos.")
        return self.logos

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, company: Company) -> Company:
        """Register a company.

        Args:
            company (Company): The company to register.

        Returns:
            Company: The stored company.

        Raises:
            MTCompanyNameTaken: If another company already uses the name.

        Notes:
            The name check happens here rather than being left to the unique
            index, so the answer is a 409 naming the clash rather than a 500
            carrying a constraint name.
        """
        self.logger.info("Registering company %s.", company.name)
        existing = await self.companies.list(size=None)
        if any(item.name.lower() == company.name.lower() for item in existing):
            self.logger.warning(
                "Refused to register %s: the name is already in use.",
                company.name,  # noqa: E501
            )
            raise MTCompanyNameTaken(
                f"A company already trades under {company.name!r}."
            )
        return await self.companies.create(company)

    async def get(self, company_id: str) -> Company:
        """Return one company.

        Args:
            company_id (str): The company to read.

        Returns:
            Company: The company.

        Raises:
            MTCompanyNotFound: If no such company exists.
        """
        self.logger.debug("Reading company %s.", company_id)
        company = await self.companies.get(company_id)
        if company is None:
            self.logger.warning("Company %s does not exist.", company_id)
            raise MTCompanyNotFound(f"No company {company_id!r} exists.")
        return company

    async def list(self, page: int = 1, size: Optional[int] = None) -> List[Company]:  # noqa: E501
        """Return a page of companies, in full.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.

        Returns:
            List[Company]: The companies, including their contact details.

        Notes:
            For authenticated staff. The list an applicant sees comes from
            :meth:`choices`, which carries nothing but names.
        """
        self.logger.debug("Listing companies: page=%d.", page)
        return await self.companies.list(page=page, size=size)

    async def choices(self) -> List[CompanyChoice]:
        """Return the companies an applicant may choose between.

        Returns:
            List[CompanyChoice]: Identifier and name only, for those still
            accepting applications.

        Notes:
            - **Served without a credential, so the shape is the protection.**
              Returning whole companies here would publish a directory of every
              agency's registered office and contact address to anybody who asks;
              :class:`~models.organisation.companies.company_choice.CompanyChoice` cannot
              carry them.
            - Companies that have closed their applications are omitted rather
              than shown greyed out: an applicant cannot act on them, and an
              option that fails on submission is worse than one that was never
              offered.
        """
        companies = await self.companies.list(size=None, accepting_only=True)
        self.logger.info("Offering %d company choice(s) to applicants.", len(companies))  # noqa: E501
        if not companies:
            self.logger.warning(
                "No company is accepting applications; the public list is empty."
            )
        return [company.to_public_choice() for company in companies]

    async def update(self, company_id: str, company: Company) -> Company:
        """Replace a company's details.

        Args:
            company_id (str): The company to change.
            company (Company): The new details.

        Returns:
            Company: The updated company.

        Raises:
            MTCompanyNotFound: If no such company exists.

        Notes:
            The identifier comes from the path, not the payload, so a
            well-formed request cannot rewrite a different company than the one
            addressed.
        """
        self.logger.info("Updating company %s.", company_id)
        updated = await self.companies.update(
            company.model_copy(update={"id": company_id})
        )
        if updated is None:
            self.logger.warning("Cannot update the absent company %s.", company_id)  # noqa: E501
            raise MTCompanyNotFound(f"No company {company_id!r} exists.")
        return updated

    async def set_accepting_applications(
        self, company_id: str, is_accepting: bool
    ) -> Company:
        """Open or close a company to new applications.

        Args:
            company_id (str): The company to change.
            is_accepting (bool): Whether it should appear on the public list.

        Returns:
            Company: The updated company.

        Raises:
            MTCompanyNotFound: If no such company exists.

        Notes:
            Closing does not touch the applications already submitted. Somebody
            who applied yesterday still deserves a decision, and silently
            discarding a queue because the agency stopped advertising would be
            a decision nobody made.
        """
        company = await self.get(company_id)
        self.logger.info(
            "Setting company %s to %s applications.",
            company_id,
            "accept" if is_accepting else "refuse",
        )
        updated = await self.companies.update(
            company.model_copy(update={"is_accepting_applications": is_accepting})  # noqa: E501
        )
        if updated is None:
            self.logger.error(
                "Company %s vanished between the read and the write.",
                company_id,  # noqa: E501
            )
            raise MTCompanyNotFound(f"No company {company_id!r} exists.")
        if not is_accepting:
            self.logger.warning(
                "Company %s no longer appears to applicants; its pending "
                "applications still need deciding.",
                company_id,
            )
        return updated

    async def set_logo(self, company_id: str, payload: bytes) -> Company:
        """Store an agency's logo and attach it to its record.

        Args:
            company_id (str): The agency the logo belongs to.
            payload (bytes): The image bytes.

        Returns:
            Company: The updated agency.

        Raises:
            MTCompanyNotFound: If no such agency exists.
            MTCompanyLogoStorageUnavailable: If the deployment has no object
                store.
            MTS3EmptyPayload: If the upload carries no bytes.
            MTS3UnsupportedContentType: If it is not an accepted image.
            MTS3PayloadTooLarge: If it exceeds the configured size.
            MTS3BucketUnavailable: If the object store cannot be reached.
            MTS3UploadFailed: If the object could not be written.

        Notes:
            The object is written **before** the record is updated, as with an
            assistant's photograph. The reverse order would leave a record
            pointing at an object that does not exist yet, so a failure between
            the two steps would show a broken image rather than the previous
            one.
        """
        logos = self._require_logo_storage()
        company = await self.get(company_id)
        previous_url = company.logo_url
        self.logger.debug(
            "Company %s currently shows %s.", company_id, previous_url or "no logo"
        )
        if not payload:
            self.logger.warning(
                "Company %s sent an empty logo; the object store will refuse it.",
                company_id,
            )
        self.logger.info(
            "Storing a %d-byte logo for company %s.", len(payload), company_id
        )
        logo_url = await logos.upload_logo(company_id, payload)
        updated = await self.companies.set_logo_url(company_id, logo_url)
        if updated is None:
            self.logger.error(
                "Company %s vanished while its logo was uploading; the object "
                "at %s is now orphaned.",
                company_id,
                logo_url,
            )
            raise MTCompanyNotFound(f"No company {company_id!r} exists.")
        await self._remove_superseded(previous_url, logo_url)
        self.logger.info("Company %s now shows %s.", company_id, logo_url)
        return updated

    async def clear_logo(self, company_id: str) -> Company:
        """Remove an agency's logo.

        Args:
            company_id (str): The agency to clear.

        Returns:
            Company: The updated agency.

        Raises:
            MTCompanyNotFound: If no such agency exists.
            MTCompanyLogoStorageUnavailable: If the deployment has no object
                store.

        Notes:
            The link is cleared first, the opposite of the upload order. What
            matters in both cases is that the record never points at a missing
            object: on upload the object must exist first, on removal the link
            must go first.
        """
        self._require_logo_storage()
        company = await self.get(company_id)
        previous_url = company.logo_url
        self.logger.debug("Clearing the logo of company %s.", company_id)
        if previous_url is None:
            self.logger.warning(
                "Company %s has no logo to clear; the record is written anyway "
                "so the caller's screen agrees with the store.",
                company_id,
            )
        updated = await self.companies.set_logo_url(company_id, None)
        if updated is None:
            self.logger.error(
                "Company %s vanished while its logo was being cleared.", company_id
            )
            raise MTCompanyNotFound(f"No company {company_id!r} exists.")
        await self._remove_superseded(previous_url, None)
        self.logger.info("Company %s no longer has a logo.", company_id)
        return updated

    async def delete(self, company_id: str) -> None:
        """Remove an agency that nobody belongs to.

        Args:
            company_id (str): The agency to remove.

        Raises:
            MTCompanyNotFound: If no such agency exists.
            MTCompanyNotEmpty: If an account or an assistant still names it.

        Notes:
            - The emptiness check names *what* is still attached rather than
              refusing flatly. "Two accounts and one assistant still belong to
              this agency" tells the caller what to do next; "cannot delete"
              leaves them guessing which of three tables to look in.
            - The logo object goes with the row, best effort. Nothing references
              it once the agency is gone, and leaving it would accumulate images
              in the bucket that no record can name.
        """
        company = await self.get(company_id)
        accounts = await self.users.count_for_company(company_id)
        assistants = await self.hcas.count_for_company(company_id)
        if accounts or assistants:
            self.logger.warning(
                "Refused to delete agency %s: %d account(s) and %d assistant(s) "
                "still belong to it.",
                company_id,
                accounts,
                assistants,
            )
            raise MTCompanyNotEmpty(
                f"Agency {company_id!r} still has {accounts} account(s) and "
                f"{assistants} assistant(s); move or remove them first."
            )
        await self.companies.delete(company_id)
        await self._remove_superseded(company.logo_url, None)
        self.logger.info("Deleted agency %s.", company_id)
