from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional, Set, Tuple

# Third-party imports
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.catalog.certification_type import CertificationType
from models.schemas.requests.catalog.certification_type_filter import (
    CertificationTypeFilter,
)
from storage.mappers.catalog.certification_type_mapper import CertificationTypeMapper
from storage.orm.catalog.certification_type_row import CertificationTypeRow
from storage.repositories.base import BaseRepository


class CertificationTypeRepository(BaseRepository[CertificationTypeRow]):
    """Reads and writes the certification catalogue.

    Attributes:
        mapper (CertificationTypeMapper): Converts between rows and models.

    Notes:
        Unlike the intervention-type catalogue this one *can* be deleted from,
        because an entry added by mistake this morning refers to nothing. The
        service refuses the delete once anybody holds the code or any service
        requires it, and offers retirement instead — the check belongs there
        rather than here, since the rows it has to count live in two other
        tables and a repository that reached into them would be a repository
        with an opinion about the domain.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        super().__init__(
            session=session,
            row_class=CertificationTypeRow,
        )
        self.mapper = CertificationTypeMapper()

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_query(
        self,
        include_inactive: bool,
        certification_filter: Optional[CertificationTypeFilter] = None,
    ) -> Select[Tuple[CertificationTypeRow]]:
        """Build the filtered select shared by ``list`` and ``count``.

        Args:
            include_inactive (bool): Whether retired entries are included.
            certification_filter (Optional[CertificationTypeFilter]): The screen's filter.
            certification_filter (CertificationTypeFilter): The screen's filter, or ``None``.

        Returns:
            Select: The filtered statement, without ordering or pagination.

        Notes:
            **``is_active`` wins over ``include_inactive`` when it is set.**
            The older switch has two states and no way to ask for the retired
            entries *on their own*; the filter has three. Unset, the switch
            still decides, so every caller that predates the filter behaves
            exactly as it did.
        """
        applied = certification_filter or CertificationTypeFilter()
        self.logger.debug(
            "Building the catalogue query from %s (include_inactive=%s).",
            applied.model_dump(exclude_none=True),
            include_inactive,
        )
        statement = select(CertificationTypeRow)
        if applied.is_active is not None:
            if include_inactive and applied.is_active:
                self.logger.warning(
                    "include_inactive asked for the retired entries and the "
                    "filter asked for the active ones; the filter wins."
                )
            statement = statement.where(
                CertificationTypeRow.is_active.is_(applied.is_active)
            )
        elif not include_inactive:
            statement = statement.where(CertificationTypeRow.is_active.is_(True))
        else:
            self.logger.info("Listing the catalogue including retired entries.")
        if applied.search:
            pattern = f"%{applied.search.strip().lower()}%"
            statement = statement.where(
                or_(
                    CertificationTypeRow.code.ilike(pattern),
                    CertificationTypeRow.label.ilike(pattern),
                    CertificationTypeRow.description.ilike(pattern),
                )
            )
        # One column each, unlike ``search``: somebody who has decided the
        # fragment is a code does not want it matched against a description.
        for fragment, column in (
            (applied.code, CertificationTypeRow.code),
            (applied.label, CertificationTypeRow.label),
        ):
            if fragment:
                statement = statement.where(
                    column.ilike(f"%{fragment.strip().lower()}%")
                )
        return statement

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, certification_type: CertificationType) -> CertificationType:  # noqa: E501
        """Insert a new qualification into the catalogue.

        Args:
            certification_type (CertificationType): The entry to store.

        Returns:
            CertificationType: The stored entry, carrying its identifier.

        Raises:
            SQLAlchemyError: If the insert fails — notably when the code is
                already taken.
        """
        self.logger.info(
            "Creating certification type %s (%s).",
            certification_type.code,
            certification_type.label,
        )
        row = self.mapper.to_row(certification_type)
        self.session.add(row)
        await self.session.flush()
        self.logger.debug("Created certification type row %s.", row.id)
        return self.mapper.to_model(row)

    async def get(self, type_id: str) -> Optional[CertificationType]:
        """Return a catalogue entry by identifier.

        Args:
            type_id (str): The identifier to look up.

        Returns:
            Optional[CertificationType]: The entry, or ``None`` when absent.
        """
        row = await self._get_row(type_id)
        if row is None:
            self.logger.warning("Certification type %s not found.", type_id)
            return None
        return self.mapper.to_model(row)

    async def get_by_code(self, code: str) -> Optional[CertificationType]:
        """Return a catalogue entry by its stable code.

        Args:
            code (str): The code to look up. Normalised before matching.

        Returns:
            Optional[CertificationType]: The entry, or ``None`` when absent.

        Notes:
            The code is upper-cased here as well as in the model, because a
            lookup takes a bare string off the wire that no model has seen.
        """
        normalized = code.strip().upper()
        self.logger.debug("Looking up certification type by code %s.", normalized)  # noqa: E501
        row = await self._fetch_one(
            select(CertificationTypeRow).where(CertificationTypeRow.code == normalized)  # noqa: E501
        )
        if row is None:
            self.logger.warning("No certification type with code %s.", normalized)  # noqa: E501
            return None
        return self.mapper.to_model(row)

    async def known_codes(self, include_inactive: bool = False) -> Set[str]:
        """Return every code the catalogue currently offers.

        Args:
            include_inactive (bool): Whether retired entries are included.

        Returns:
            Set[str]: The codes, upper-cased.

        Notes:
            A set rather than a list, and one query rather than one per code.
            This is what the services validate a requirement against — a
            catalogue entry saved with five codes would otherwise cost five
            round trips to say "all fine".
        """
        rows = await self._fetch_all(self._build_query(include_inactive))
        codes = {row.code for row in rows}
        self.logger.debug("The catalogue offers %d code(s).", len(codes))
        if not codes:
            self.logger.warning(
                "The certification catalogue is empty; any requirement naming "
                "a code will be refused."
            )
        return codes

    async def update(
        self, certification_type: CertificationType
    ) -> Optional[CertificationType]:
        """Update an existing catalogue entry.

        Args:
            certification_type (CertificationType): The entry to store,
                carrying its identifier.

        Returns:
            Optional[CertificationType]: The updated entry, or ``None`` when no
            row matched.

        Raises:
            SQLAlchemyError: If the update fails.
        """
        if certification_type.id is None:
            self.logger.warning("Update requested for a catalogue entry with no id.")
            return None
        row = await self._get_row(certification_type.id)
        if row is None:
            self.logger.warning(
                "Update requested for absent certification type %s.",
                certification_type.id,
            )
            return None
        self.mapper.apply_to_row(row, certification_type)
        await self.session.flush()
        self.logger.info("Updated certification type %s.", certification_type.id)  # noqa: E501
        return self.mapper.to_model(row)

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        include_inactive: bool = False,
        certification_filter: Optional[CertificationTypeFilter] = None,
    ) -> List[CertificationType]:
        """Return a page of the catalogue.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            include_inactive (bool): Whether retired entries are included.

        Returns:
            List[CertificationType]: The matching entries, ordered by label.

        Notes:
            Ordered by label rather than by code, because that is what a
            manager scanning the list reads. Retired entries are hidden by
            default so a quote-building screen offers only what may still be
            required.
        """
        self.logger.debug(
            "Listing certification types: page=%d include_inactive=%s.",
            page,
            include_inactive,
        )
        statement = self._build_query(include_inactive, certification_filter).order_by(
            CertificationTypeRow.label
        )
        rows = await self._fetch_all(self._paginate(statement, page, size))
        if not rows:
            self.logger.warning("No certification type matched the query.")
        return self.mapper.to_models(rows)

    async def count(
        self,
        include_inactive: bool = False,
        certification_filter: Optional[CertificationTypeFilter] = None,
    ) -> int:
        """Return how many catalogue entries match a query.

        Args:
            include_inactive (bool): Whether retired entries are counted.
            certification_filter (Optional[CertificationTypeFilter]): The screen's filter, so a page
                and its total can never come from different filters.

        Returns:
            int: The number of matching entries.
        """
        return await self._count(
            self._build_query(include_inactive, certification_filter)
        )

    async def delete(self, type_id: str) -> bool:
        """Remove a catalogue entry outright.

        Args:
            type_id (str): The entry to remove.

        Returns:
            bool: ``True`` when a row was removed, ``False`` when none matched.

        Notes:
            Whether the entry *may* be removed is the service's question, not
            this one's: the rows that would be orphaned live in ``hcas`` and
            ``intervention_types``, and no foreign key protects them.
        """
        removed = await self._delete_row(type_id)
        if removed:
            self.logger.info("Deleted certification type %s.", type_id)
        else:
            self.logger.warning(
                "Delete requested for absent certification type %s.", type_id
            )
        return removed
