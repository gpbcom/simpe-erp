from __future__ import annotations

# Standard library imports
from datetime import date
from logging import Logger, getLogger
from typing import List, Optional, Tuple
from uuid import uuid4

# Third-party imports
from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import ContractType
from models.people.availability_slot import AvailabilitySlot
from models.people.certification import Certification
from models.people.hca import Hca
from storage.mappers.hca_mapper import HcaMapper
from storage.orm.availability_row import AvailabilityRow
from storage.orm.certification_row import CertificationRow
from storage.orm.hca_row import HcaRow
from storage.repositories.base import BaseRepository


class HcaRepository(BaseRepository[HcaRow]):
    """Reads and writes Home Care Assistants.

    Attributes:
        mapper (HcaMapper): Converts between rows and domain models.

    Notes:
        Two mutation paths are deliberately narrow rather than general.
        :meth:`set_employment` is the only way a manager changes an assistant,
        and :meth:`add_availability` the only way an absence is filed. A single
        general update would let either caller overwrite fields they have no
        business touching.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        resolved_logger = logger if logger else getLogger(__name__)
        super().__init__(session=session, row_class=HcaRow, logger=resolved_logger)
        self.mapper = HcaMapper(logger=resolved_logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_query(
        self,
        search: Optional[str] = None,
        contract_type: Optional[ContractType] = None,
    ) -> Select[Tuple[HcaRow]]:
        """Build the filtered select shared by ``list`` and ``count``.

        Args:
            search (Optional[str]): Case-insensitive fragment.
            contract_type (Optional[ContractType]): Restrict to one contract.

        Returns:
            Select[tuple[HcaRow]]: The filtered statement, without ordering or pagination.
        """
        statement = select(HcaRow)
        if contract_type is not None:
            statement = statement.where(HcaRow.contract_type == contract_type.value)  # noqa: E501
        if search:
            pattern = f"%{search.strip().lower()}%"
            statement: Select[tuple[HcaRow]] = statement.where(
                or_(
                    HcaRow.first_name.ilike(pattern),
                    HcaRow.last_name.ilike(pattern),
                    HcaRow.email.ilike(pattern),
                    HcaRow.city.ilike(pattern),
                )
            )
        return statement

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, hca: Hca) -> Hca:
        """Insert a new assistant.

        Args:
            hca (Hca): The assistant to store.

        Returns:
            Hca: The stored assistant, carrying its generated identifier.

        Raises:
            SQLAlchemyError: If the insert fails.
        """
        self.logger.info("Creating hca %s.", hca.full_name())
        row = self.mapper.to_row(hca)
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        self.logger.debug("Created hca row %s.", row.id)
        return self.mapper.to_model(row)

    async def get(self, hca_id: str) -> Optional[Hca]:
        """Return an assistant by identifier.

        Args:
            hca_id (str): The identifier to look up.

        Returns:
            Optional[Hca]: The assistant, or ``None`` when absent.
        """
        row = await self._get_row(hca_id)
        if row is None:
            self.logger.warning("Hca %s not found.", hca_id)
            return None
        return self.mapper.to_model(row)

    async def update(self, hca: Hca) -> Optional[Hca]:
        """Update an existing assistant in full.

        Args:
            hca (Hca): The assistant to store, carrying its identifier.

        Returns:
            Optional[Hca]: The updated assistant, or ``None`` when absent.

        Raises:
            SQLAlchemyError: If the update fails.
        """
        if hca.id is None:
            self.logger.warning("Update requested for an hca with no id.")
            return None
        row = await self._get_row(hca.id)
        if row is None:
            self.logger.warning("Update requested for absent hca %s.", hca.id)
            return None
        self.mapper.apply_to_row(row, hca)
        await self.session.flush()
        await self.session.refresh(row)
        self.logger.info("Updated hca %s.", hca.id)
        return self.mapper.to_model(row)

    async def set_photo_url(
        self, hca_id: str, photo_url: Optional[str]
    ) -> Optional[Hca]:
        """Point an assistant's record at a stored photograph, or clear it.

        Args:
            hca_id (str): The assistant to change.
            photo_url (Optional[str]): The object-store URL, or ``None`` to
                remove the photograph.

        Returns:
            Optional[Hca]: The updated assistant, or ``None`` when absent.

        Raises:
            SQLAlchemyError: If the update fails.

        Notes:
            A narrow method, like the other mutations here: the photograph is
            uploaded on its own endpoint, and routing it through a general
            update would let a stale payload overwrite the contact details or
            the availability at the same time.
        """
        row = await self._get_row(hca_id)
        if row is None:
            self.logger.warning("Photograph link requested for absent hca %s.", hca_id)
            return None
        self.logger.info("Setting the photograph of hca %s to %s.", hca_id, photo_url)
        row.photo_url = photo_url
        await self.session.flush()
        await self.session.refresh(row)
        return self.mapper.to_model(row)

    async def set_employment(
        self,
        hca_id: str,
        contract_type: ContractType,
        certifications: List[Certification],
    ) -> Optional[Hca]:
        """Replace an assistant's contract type and qualifications.

        Args:
            hca_id (str): The assistant to change.
            contract_type (ContractType): The new employment contract.
            certifications (List[Certification]): The qualifications now held.

        Returns:
            Optional[Hca]: The updated assistant, or ``None`` when absent.

        Raises:
            SQLAlchemyError: If the update fails.

        Notes:
            - These are the only two fields a manager may change. Enforcing that
              through a narrow method — rather than trusting the caller to send a
              partial payload — means no manager-facing route can reach the
              contact details, the home address or the availability.
            - The certifications are replaced wholesale, matching the edit form's
              semantics: what is sent is what the assistant now holds.
        """
        row = await self._get_row(hca_id)
        if row is None:
            self.logger.warning(
                "Employment change requested for absent hca %s.", hca_id
            )
            return None
        self.logger.info(
            "Setting hca %s employment: contract=%s certifications=%d.",
            hca_id,
            contract_type.value,
            len(certifications),
        )
        row.contract_type = contract_type.value
        row.certifications = [
            CertificationRow(
                id=str(uuid4()),
                hca_id=hca_id,
                name=certification.name,
                issuer=certification.issuer,
                obtained_on=certification.obtained_on,
                expires_on=certification.expires_on,
            )
            for certification in certifications
        ]
        await self.session.flush()
        await self.session.refresh(row)
        return self.mapper.to_model(row)

    async def add_availability(
        self, hca_id: str, slot: AvailabilitySlot
    ) -> Optional[AvailabilitySlot]:
        """File an absence for an assistant.

        Args:
            hca_id (str): The assistant the absence belongs to.
            slot (AvailabilitySlot): The absence to record.

        Returns:
            Optional[AvailabilitySlot]: The stored absence with its generated
            identifier, or ``None`` when the assistant is absent.

        Raises:
            SQLAlchemyError: If the insert fails.

        Notes:
            The assistant identifier comes from the argument, never from the
            payload: an assistant must not be able to file an absence against a
            colleague by naming them in the body.
        """
        row = await self._get_row(hca_id)
        if row is None:
            self.logger.warning("Availability filed for absent hca %s.", hca_id)
            return None
        slot_id = str(uuid4())
        self.logger.info(
            "Filing %s availability %s for hca %s (%s to %s).",
            slot.kind.value,
            slot_id,
            hca_id,
            slot.start_date,
            slot.end_date,
        )
        slot_row = AvailabilityRow(
            id=slot_id,
            hca_id=hca_id,
            start_date=slot.start_date,
            end_date=slot.end_date,
            kind=slot.kind.value,
            start_time=slot.start_time,
            end_time=slot.end_time,
            note=slot.note,
        )
        self.session.add(slot_row)
        await self.session.flush()
        return slot.model_copy(update={"id": slot_id, "hca_id": hca_id})

    async def remove_availability(self, hca_id: str, slot_id: str) -> bool:
        """Withdraw a filed absence.

        Args:
            hca_id (str): The assistant the absence belongs to.
            slot_id (str): The absence to withdraw.

        Returns:
            bool: ``True`` when the absence was removed.

        Notes:
            The assistant identifier is part of the lookup, not just the slot
            identifier. Without it, knowing a slot id would be enough to delete
            another assistant's absence.
        """
        statement = select(AvailabilityRow).where(
            AvailabilityRow.id == slot_id,
            AvailabilityRow.hca_id == hca_id,
        )
        try:
            result = await self.session.execute(statement)
            slot_row = result.scalars().first()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Error loading availability %s for hca %s: %s.",
                slot_id,
                hca_id,
                exc,
            )
            return False
        if slot_row is None:
            self.logger.warning(
                "Availability %s not found for hca %s.", slot_id, hca_id
            )
            return False
        await self.session.delete(slot_row)
        await self.session.flush()
        self.logger.info("Removed availability %s for hca %s.", slot_id, hca_id)
        return True

    async def list_availability(
        self, hca_id: str, start: Optional[date] = None, end: Optional[date] = None
    ) -> List[AvailabilitySlot]:
        """Return an assistant's absences, optionally within a window.

        Args:
            hca_id (str): The assistant to read.
            start (Optional[date]): Earliest day of interest.
            end (Optional[date]): Latest day of interest.

        Returns:
            List[AvailabilitySlot]: The matching absences, oldest first.

        Notes:
            The overlap test compares the slot's end against the window start
            and its start against the window end. Comparing only the start
            would miss an absence that began before the window and runs into
            it — precisely the case that breaks a planning.
        """
        self.logger.debug(
            "Listing availability for hca %s between %s and %s.",
            hca_id,
            start,
            end,
        )
        statement = select(AvailabilityRow).where(AvailabilityRow.hca_id == hca_id)
        if start is not None:
            statement = statement.where(AvailabilityRow.end_date >= start)
        if end is not None:
            statement = statement.where(AvailabilityRow.start_date <= end)
        statement = statement.order_by(AvailabilityRow.start_date)
        try:
            result = await self.session.execute(statement)
            rows = result.scalars().all()
        except SQLAlchemyError as exc:
            self.logger.error("Error listing availability for hca %s: %s.", hca_id, exc)
            return []
        return [
            AvailabilitySlot(
                id=row.id,
                hca_id=row.hca_id,
                start_date=row.start_date,
                end_date=row.end_date,
                kind=row.kind,
                start_time=row.start_time,
                end_time=row.end_time,
                note=row.note,
            )
            for row in rows
        ]

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
            search (Optional[str]): Case-insensitive fragment matched against
                the names, the email and the city.
            contract_type (Optional[ContractType]): Restrict to one contract.

        Returns:
            List[Hca]: The matching assistants, ordered by family name.
        """
        self.logger.debug(
            "Listing hcas: page=%d search=%r contract=%s.",
            page,
            search,
            contract_type.value if contract_type else None,
        )
        statement = self._build_query(search=search, contract_type=contract_type)
        statement = statement.order_by(HcaRow.last_name, HcaRow.first_name)
        rows = await self._fetch_all(self._paginate(statement, page, size))
        if not rows:
            self.logger.warning("No hca matched the query.")
        return self.mapper.to_models(rows)

    async def list_all(self) -> List[Hca]:
        """Return every assistant.

        Returns:
            List[Hca]: Every assistant, ordered by family name.

        Notes:
            Unpaginated by design: the planning computation needs the whole
            workforce in one go, and paging through it would produce a plan
            built from a moving target.
        """
        self.logger.debug("Listing every hca for a planning run.")
        statement = select(HcaRow).order_by(HcaRow.last_name, HcaRow.first_name)
        rows = await self._fetch_all(statement)
        self.logger.info("Loaded %d hca(s) for planning.", len(rows))
        if not rows:
            self.logger.warning(
                "No hca is registered; a planning run would have nobody to assign."
            )
        return self.mapper.to_models(rows)

    async def count(
        self,
        search: Optional[str] = None,
        contract_type: Optional[ContractType] = None,
    ) -> int:
        """Return how many assistants match a query.

        Args:
            search (Optional[str]): Case-insensitive fragment.
            contract_type (Optional[ContractType]): Restrict to one contract.

        Returns:
            int: The number of matching assistants.
        """
        return await self._count(
            self._build_query(search=search, contract_type=contract_type)
        )

    async def delete(self, hca_id: str) -> bool:
        """Delete an assistant.

        Args:
            hca_id (str): The assistant to delete.

        Returns:
            bool: ``True`` when a row was deleted.

        Raises:
            SQLAlchemyError: If an account still references the assistant.
        """
        try:
            return await self._delete_row(hca_id)
        except SQLAlchemyError as exc:
            self.logger.error("Error deleting hca %s: %s.", hca_id, exc)
            raise

    async def count_for_company(self, company_id: str) -> int:
        """Return how many assistants belong to one agency.

        Args:
            company_id (str): The agency to count for.

        Returns:
            int: The number of assistants.

        Notes:
            A count rather than a list: the caller only needs to know whether
            the agency is empty, and reading every assistant to find that out
            would be a page of records fetched to be thrown away.
        """
        found = await self._count(select(HcaRow).where(HcaRow.company_id == company_id))
        self.logger.debug("Agency %s has %d assistant(s).", company_id, found)
        return found
