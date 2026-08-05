from __future__ import annotations

# Standard library imports
from datetime import date
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.planning.intervention import Intervention
from storage.mappers.intervention_mapper import InterventionMapper
from storage.orm.intervention_row import InterventionRow
from storage.repositories.base import BaseRepository


class InterventionRepository(BaseRepository[InterventionRow]):
    """Reads and writes scheduled visits.

    Attributes:
        mapper (InterventionMapper): Converts between rows and domain models.

    Notes:
        Every read is scoped by assistant or by period. There is deliberately
        no "all interventions" method: the one query nobody should be able to
        make casually is the one that returns every assistant's diary at once.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        resolved_logger = logger if logger else getLogger(__name__)
        super().__init__(
            session=session, row_class=InterventionRow, logger=resolved_logger
        )
        self.mapper = InterventionMapper(logger=resolved_logger)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def replace_for_period(
        self,
        period_start: date,
        period_end: date,
        interventions: List[Intervention],
    ) -> int:
        """Swap the plan for a period for a freshly computed one.

        Args:
            period_start (date): First day replaced, inclusive.
            period_end (date): Last day replaced, inclusive.
            interventions (List[Intervention]): The new plan.

        Returns:
            int: How many visits were written.

        Notes:
            The delete and the insert happen in one transaction, so a period is
            never briefly empty — an assistant refreshing mid-replan sees the
            old plan or the new one, never a blank week.

            Scoped to the period rather than the run: a re-plan of one week
            must not disturb the week after it, which a different run produced.
        """
        self.logger.info(
            "Replacing the plan for %s to %s with %d visit(s).",
            period_start,
            period_end,
            len(interventions),
        )
        await self.session.execute(
            delete(InterventionRow).where(
                InterventionRow.day >= period_start,
                InterventionRow.day <= period_end,
            )
        )
        for intervention in interventions:
            self.session.add(self.mapper.to_row(intervention))
        await self.session.flush()
        if not interventions:
            self.logger.warning(
                "The new plan for %s to %s is empty; every calendar in that "
                "period is now blank.",
                period_start,
                period_end,
            )
        return len(interventions)

    async def list_for_hca(
        self, hca_id: str, period_start: date, period_end: date
    ) -> List[Intervention]:
        """Return one assistant's visits over a period.

        Args:
            hca_id (str): The assistant whose diary is being read.
            period_start (date): First day of interest, inclusive.
            period_end (date): Last day of interest, inclusive.

        Returns:
            List[Intervention]: Their visits, in day and time order.

        Notes:
            The assistant is part of the query, not a filter applied after. An
            assistant may read only their own planning, and a method that
            returned everybody's and left the caller to narrow it would make
            that a discipline rather than a property.
        """
        self.logger.debug(
            "Loading the diary of assistant %s from %s to %s.",
            hca_id,
            period_start,
            period_end,
        )
        statement = (
            select(InterventionRow)
            .where(
                InterventionRow.hca_id == hca_id,
                InterventionRow.day >= period_start,
                InterventionRow.day <= period_end,
            )
            .order_by(InterventionRow.day, InterventionRow.start_time)
        )
        rows = await self._fetch_all(statement)
        if not rows:
            self.logger.warning(
                "Assistant %s has no visit between %s and %s.",
                hca_id,
                period_start,
                period_end,
            )
        return [self.mapper.to_model(row) for row in rows]

    async def list_hca_ids_for_period(
        self, period_start: date, period_end: date
    ) -> List[str]:
        """Return which assistants have work in a period.

        Args:
            period_start (date): First day of interest, inclusive.
            period_end (date): Last day of interest, inclusive.

        Returns:
            List[str]: The assistants' identifiers.

        Notes:
            Used to build the manager's whole-workforce view without loading
            every visit first: the diaries are then fetched one assistant at a
            time, through the same scoped read an assistant would use.
        """
        statement = (
            select(InterventionRow.hca_id)
            .where(
                InterventionRow.day >= period_start,
                InterventionRow.day <= period_end,
            )
            .distinct()
        )
        try:
            result = await self.session.execute(statement)
            identifiers = [row[0] for row in result.all()]
        except Exception as exc:  # noqa: BLE001 - reported as an empty period
            self.logger.error(
                "Error listing the assistants planned between %s and %s: %s.",
                period_start,
                period_end,
                exc,
            )
            return []
        self.logger.debug(
            "%d assistant(s) have work between %s and %s.",
            len(identifiers),
            period_start,
            period_end,
        )
        return identifiers

    async def count_for_period(self, period_start: date, period_end: date) -> int:
        """Return how many visits are planned in a period.

        Args:
            period_start (date): First day of interest, inclusive.
            period_end (date): Last day of interest, inclusive.

        Returns:
            int: The number of visits.
        """
        return await self._count(
            select(InterventionRow).where(
                InterventionRow.day >= period_start,
                InterventionRow.day <= period_end,
            )
        )
