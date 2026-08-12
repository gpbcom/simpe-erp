from __future__ import annotations

# Standard library imports
from decimal import Decimal
from logging import Logger, getLogger
from typing import Dict, List, Optional, Tuple

# Third-party imports
from sqlalchemy import Select, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.schemas.requests.catalog.intervention_type_filter import (
    InterventionTypeFilter,
)
from storage.mappers.planning.intervention_mapper import InterventionMapper
from storage.orm.catalog.intervention_type_row import InterventionTypeRow
from storage.repositories.base import BaseRepository


class InterventionTypeRepository(BaseRepository[InterventionTypeRow]):
    """Reads and writes the intervention-type catalog.

    Attributes:
        mapper (InterventionMapper): Converts between rows and models.

    Notes:
        There is no delete. A type is retired with ``is_active`` instead,
        because a quote issued last year still references it and removing the
        row would make that quote unreprintable.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        super().__init__(
            session=session,
            row_class=InterventionTypeRow,
        )
        self.mapper = InterventionMapper()

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_query(
        self,
        include_inactive: bool,
        type_filter: Optional[InterventionTypeFilter] = None,
    ) -> Select[Tuple[InterventionTypeRow]]:
        """Build the filtered select shared by ``list`` and ``count``.

        Args:
            include_inactive (bool): Whether retired entries are included.
            type_filter (Optional[InterventionTypeFilter]): The screen's filter.
            type_filter (InterventionTypeFilter): The screen's filter, or ``None``.

        Returns:
            Select: The filtered statement, without ordering or pagination.

        Notes:
            **``is_active`` wins over ``include_inactive`` when it is set.**
            The older switch has two states and no way to ask for the retired
            entries *on their own*; the filter has three. Unset, the switch
            still decides, so every caller that predates the filter behaves
            exactly as it did.
        """
        applied = type_filter or InterventionTypeFilter()
        self.logger.debug(
            "Building the catalogue query from %s (include_inactive=%s).",
            applied.model_dump(exclude_none=True),
            include_inactive,
        )
        statement = select(InterventionTypeRow)
        if applied.is_active is not None:
            if include_inactive and applied.is_active:
                self.logger.warning(
                    "include_inactive asked for the retired entries and the "
                    "filter asked for the active ones; the filter wins."
                )
            statement = statement.where(
                InterventionTypeRow.is_active.is_(applied.is_active)
            )
        elif not include_inactive:
            statement = statement.where(InterventionTypeRow.is_active.is_(True))
        else:
            self.logger.info("Listing the catalogue including retired entries.")
        if applied.search:
            pattern = f"%{applied.search.strip().lower()}%"
            statement = statement.where(
                or_(
                    InterventionTypeRow.code.ilike(pattern),
                    InterventionTypeRow.name.ilike(pattern),
                    InterventionTypeRow.description.ilike(pattern),
                )
            )
        # One column each, unlike ``search``: somebody who has decided the
        # fragment is a code does not want it matched against a description.
        for fragment, column in (
            (applied.code, InterventionTypeRow.code),
            (applied.name, InterventionTypeRow.name),
        ):
            if fragment:
                statement = statement.where(
                    column.ilike(f"%{fragment.strip().lower()}%")
                )
        if applied.service_category is not None:
            statement = statement.where(
                InterventionTypeRow.service_category == applied.service_category.value
            )
        return statement

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, intervention_type: InterventionType) -> InterventionType:  # noqa: E501
        """Insert a new type into the catalog.

        Args:
            intervention_type (InterventionType): The type to store.

        Returns:
            InterventionType: The stored type, carrying its identifier.

        Raises:
            SQLAlchemyError: If the insert fails — notably when the name or the
                code is already taken.
        """
        self.logger.info(
            "Creating intervention type %s (%s).",
            intervention_type.name,
            intervention_type.code,
        )
        row = self.mapper.to_type_row(intervention_type)
        self.session.add(row)
        await self.session.flush()
        self.logger.debug("Created intervention type row %s.", row.id)
        return self.mapper.to_type_model(row)

    async def get(self, type_id: str) -> Optional[InterventionType]:
        """Return a type by identifier.

        Args:
            type_id (str): The identifier to look up.

        Returns:
            Optional[InterventionType]: The type, or ``None`` when absent.
        """
        row = await self._get_row(type_id)
        if row is None:
            self.logger.warning("Intervention type %s not found.", type_id)
            return None
        return self.mapper.to_type_model(row)

    async def get_by_code(self, code: str) -> Optional[InterventionType]:
        """Return a type by its stable code.

        Args:
            code (str): The code to look up. Matched case-insensitively.

        Returns:
            Optional[InterventionType]: The type, or ``None`` when absent.
        """
        normalized = code.strip().upper()
        self.logger.debug("Looking up intervention type by code %s.", normalized)  # noqa: E501
        row = await self._fetch_one(
            select(InterventionTypeRow).where(InterventionTypeRow.code == normalized)  # noqa: E501
        )
        if row is None:
            self.logger.warning("No intervention type with code %s.", normalized)  # noqa: E501
            return None
        return self.mapper.to_type_model(row)

    async def get_many(self, type_ids: List[str]) -> Dict[str, InterventionType]:  # noqa: E501
        """Return several types at once, keyed by identifier.

        Args:
            type_ids (List[str]): The identifiers to look up.

        Returns:
            Dict[str, InterventionType]: The types found, keyed by identifier.
            Identifiers with no matching row are simply absent.

        Notes:
            Pricing a quote needs the type behind every line. Fetching them one
            at a time would issue one query per line; this is the single query
            the pricing service uses instead.
        """
        if not type_ids:
            return {}
        unique_ids = list(dict.fromkeys(type_ids))
        self.logger.debug("Loading %d intervention type(s).", len(unique_ids))
        rows = await self._fetch_all(
            select(InterventionTypeRow).where(InterventionTypeRow.id.in_(unique_ids))
        )
        found = {row.id: self.mapper.to_type_model(row) for row in rows}
        missing = set(unique_ids) - set(found)
        if missing:
            self.logger.warning(
                "%d intervention type(s) referenced but not found: %s.",
                len(missing),
                ", ".join(sorted(missing)),
            )
        return found

    async def update(
        self, intervention_type: InterventionType
    ) -> Optional[InterventionType]:
        """Update an existing type.

        Args:
            intervention_type (InterventionType): The type to store, carrying
                its identifier.

        Returns:
            Optional[InterventionType]: The updated type, or ``None`` when no
            row matched.

        Raises:
            SQLAlchemyError: If the update fails.
        """
        if intervention_type.id is None:
            self.logger.warning("Update requested for a type with no id.")
            return None
        row = await self._get_row(intervention_type.id)
        if row is None:
            self.logger.warning(
                "Update requested for absent intervention type %s.",
                intervention_type.id,
            )
            return None
        self.mapper.apply_to_type_row(row, intervention_type)
        await self.session.flush()
        self.logger.info("Updated intervention type %s.", intervention_type.id)
        return self.mapper.to_type_model(row)

    async def set_rate(
        self, type_id: str, base_hourly_rate_ht: Optional[Decimal]
    ) -> Optional[InterventionType]:
        """Change a type's hourly rate.

        Args:
            type_id (str): The type to change.
            base_hourly_rate_ht (Optional[Decimal]): The new rate, or ``None``
                to bill the agency default.

        Returns:
            Optional[InterventionType]: The updated type, or ``None`` when
            absent.

        Notes:
            A narrow method: repricing is the one change a manager makes on its
            own, and routing it through a full update would risk clobbering the
            category — which would change the VAT rate as a side effect.

            Existing quotes are unaffected: their lines carry the prices that
            were computed when they were issued, not a reference to this rate.
        """
        row = await self._get_row(type_id)
        if row is None:
            self.logger.warning("Rate change requested for absent type %s.", type_id)
            return None
        self.logger.info(
            "Setting intervention type %s rate to %s.", type_id, base_hourly_rate_ht
        )
        row.base_hourly_rate_ht = base_hourly_rate_ht
        await self.session.flush()
        return self.mapper.to_type_model(row)

    async def set_active(
        self, type_id: str, is_active: bool
    ) -> Optional[InterventionType]:
        """Retire or restore a type.

        Args:
            type_id (str): The type to change.
            is_active (bool): Whether it may be put on a new quote.

        Returns:
            Optional[InterventionType]: The updated type, or ``None`` when
            absent.
        """
        row = await self._get_row(type_id)
        if row is None:
            self.logger.warning(
                "Activation change requested for absent type %s.", type_id
            )
            return None
        self.logger.info(
            "Setting intervention type %s active to %s.", type_id, is_active
        )
        row.is_active = is_active
        await self.session.flush()
        return self.mapper.to_type_model(row)

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        include_inactive: bool = False,
        type_filter: Optional[InterventionTypeFilter] = None,
    ) -> List[InterventionType]:
        """Return a page of the catalog.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            include_inactive (bool): Whether retired types are included.

        Returns:
            List[InterventionType]: The matching types, ordered by name.

        Notes:
            Retired types are hidden by default, so a quote-building screen
            offers only what may still be sold; a catalog-administration screen
            asks for them explicitly.
        """
        self.logger.debug(
            "Listing intervention types: page=%d include_inactive=%s.",
            page,
            include_inactive,
        )
        statement = self._build_query(include_inactive, type_filter).order_by(
            InterventionTypeRow.name
        )
        rows = await self._fetch_all(self._paginate(statement, page, size))
        if not rows:
            self.logger.warning("No intervention type matched the query.")
        return self.mapper.to_type_models(rows)

    async def count(
        self,
        include_inactive: bool = False,
        type_filter: Optional[InterventionTypeFilter] = None,
    ) -> int:
        """Return how many types match a query.

        Args:
            include_inactive (bool): Whether retired types are counted.

        Returns:
            int: The number of matching types.
        """
        return await self._count(self._build_query(include_inactive, type_filter))

    async def ensure_indexes(self) -> None:
        """Verify the catalog's uniqueness constraints are in place.

        Notes:
            The indexes are created by the migration; this only reports on
            them, so a database that drifted from its migrations is visible in
            the logs rather than discovered when a duplicate slips through.
        """
        try:
            await self._count(select(InterventionTypeRow))
            self.logger.debug("Intervention-type catalog is reachable.")
        except SQLAlchemyError as exc:
            self.logger.error("Intervention-type catalog is unreachable: %s.", exc)
