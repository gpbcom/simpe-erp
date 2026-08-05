from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import PlanningRunStatus
from models.planning.planning_run import PlanningRun
from storage.mappers.planning_run_mapper import PlanningRunMapper
from storage.orm.planning_run_row import PlanningRunRow
from storage.repositories.base import BaseRepository


class PlanningRunRepository(BaseRepository[PlanningRunRow]):
    """Reads and writes planning-run records.

    Attributes:
        mapper (PlanningRunMapper): Converts between rows and domain models.

    Notes:
        The run is what makes a long solve pollable. It is written before the
        solver starts and updated when it finishes, so a client that asked for
        a planning always has something to ask about.
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
            session=session, row_class=PlanningRunRow, logger=resolved_logger
        )
        self.mapper = PlanningRunMapper(logger=resolved_logger)

    ##########################
    # Publicly Exposed Methods
    ##########################

    async def create(self, run: PlanningRun) -> PlanningRun:
        """Record a new run, durably.

        Args:
            run (PlanningRun): The run to record.

        Returns:
            PlanningRun: The stored run, carrying its identifier.

        Notes:
            - **Commits, where every other create only flushes.** The endpoint
              answers 202 with this run's identifier and schedules a background
              job against it; that job opens its own session, so a row that is
              only flushed is invisible to it and the job fails immediately with
              "no such run" while the caller polls a record that never moves.
            - Committing here is the narrow exception to one-transaction-per-
              request, and it is the right one: a 202 is a promise that the
              identifier is real, so it has to be real before the response is
              written.
        """
        self.logger.info(
            "Recording a planning run for %s to %s, requested by %s.",
            run.period_start,
            run.period_end,
            run.requested_by,
        )
        row = self.mapper.to_row(run)
        self.session.add(row)
        await self.session.flush()
        stored = self.mapper.to_model(row)
        await self.session.commit()
        self.logger.debug("Planning run %s is committed and pollable.", stored.id)
        return stored

    async def get(self, run_id: str) -> Optional[PlanningRun]:
        """Return a run by identifier.

        Args:
            run_id (str): The identifier to look up.

        Returns:
            Optional[PlanningRun]: The run, or ``None`` when absent.
        """
        row = await self._get_row(run_id)
        if row is None:
            self.logger.warning("Planning run %s not found.", run_id)
            return None
        return self.mapper.to_model(row)

    async def update(self, run: PlanningRun) -> Optional[PlanningRun]:
        """Record a run's progress or its result.

        Args:
            run (PlanningRun): The run to store, carrying its identifier.

        Returns:
            Optional[PlanningRun]: The updated run, or ``None`` when absent.
        """
        if run.id is None:
            self.logger.warning("Update requested for a run with no id.")
            return None
        row = await self._get_row(run.id)
        if row is None:
            self.logger.warning("Update requested for absent run %s.", run.id)
            return None
        self.mapper.apply_to_row(row, run)
        await self.session.flush()
        self.logger.info("Planning run %s is now %s.", run.id, run.status.value)
        return self.mapper.to_model(row)

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        status: Optional[PlanningRunStatus] = None,
    ) -> List[PlanningRun]:
        """Return a page of runs, most recent period first.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            status (Optional[PlanningRunStatus]): Restrict to one status.

        Returns:
            List[PlanningRun]: The matching runs.
        """
        self.logger.debug(
            "Listing planning runs: page=%d status=%s.",
            page,
            status.value if status else None,
        )
        statement = select(PlanningRunRow)
        if status is not None:
            statement = statement.where(PlanningRunRow.status == status.value)
        statement = statement.order_by(PlanningRunRow.period_start.desc())
        rows = await self._fetch_all(self._paginate(statement, page, size))
        if not rows:
            self.logger.warning("No planning run matched the query.")
        return [self.mapper.to_model(row) for row in rows]

    async def latest_succeeded(self) -> Optional[PlanningRun]:
        """Return the most recent run that produced a plan.

        Returns:
            Optional[PlanningRun]: The run, or ``None`` when none has ever
            succeeded.

        Notes:
            The planning views read from whichever run last succeeded, so a
            failed re-plan leaves the previous plan standing rather than
            emptying everybody's calendar.
        """
        statement = (
            select(PlanningRunRow)
            .where(PlanningRunRow.status == PlanningRunStatus.SUCCEEDED.value)
            .order_by(PlanningRunRow.finished_at.desc())
        )
        row = await self._fetch_one(statement)
        if row is None:
            self.logger.warning("No planning run has ever succeeded.")
            return None
        return self.mapper.to_model(row)
