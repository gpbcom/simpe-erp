from __future__ import annotations

# Standard library imports
from datetime import datetime
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.billing.billing_run import BillingRun
from models.enums import BillingRunStatus
from storage.mappers.billing.billing_run_mapper import BillingRunMapper
from storage.orm.billing.billing_run_row import BillingRunRow
from storage.repositories.base import BaseRepository


class BillingRunRepository(BaseRepository[BillingRunRow]):
    """Reads and writes the record of a request to bill a period.

    Attributes:
        mapper (BillingRunMapper): Converts between the row and the model.

    Notes:
        The run is written **before** the work is queued, which is what lets the
        endpoint answer 202 with an identifier a caller can really poll: an
        unreachable broker leaves the run sitting at pending rather than losing
        it. The planning run is recorded the same way and for the same reason.
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
            row_class=BillingRunRow,
        )
        self.mapper = BillingRunMapper()

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, run: BillingRun) -> BillingRun:
        """Record a request to bill a period.

        Args:
            run (BillingRun): The run to record.

        Returns:
            BillingRun: The stored run, carrying its identifier.
        """
        self.logger.info(
            "Recording a billing run for agency %s over %s..%s (%s).",
            run.company_id,
            run.period_start,
            run.period_end,
            run.periodicity.value,
        )
        row = self.mapper.to_row(run)
        self.session.add(row)
        await self.session.flush()
        self.logger.debug("Stored billing run row %s.", row.id)
        return self.mapper.to_model(row)

    async def get(self, run_id: str) -> Optional[BillingRun]:
        """Return one run.

        Args:
            run_id (str): The run to read.

        Returns:
            Optional[BillingRun]: The run, or ``None`` when there is no such
            row.
        """
        self.logger.debug("Fetching billing run %s.", run_id)
        row = await self._get_row(run_id)
        if row is None:
            self.logger.warning("No billing run found with id %s.", run_id)
            return None
        return self.mapper.to_model(row)

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        company_id: Optional[str] = None,
    ) -> List[BillingRun]:
        """Return a page of runs, most recently requested first.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            company_id (Optional[str]): Restrict to one agency's runs.

        Returns:
            List[BillingRun]: The matching runs.
        """
        statement = select(BillingRunRow)
        if company_id is not None:
            statement = statement.where(BillingRunRow.company_id == company_id)
        statement = statement.order_by(BillingRunRow.requested_at.desc())
        rows = await self._fetch_all(self._paginate(statement, page, size))
        self.logger.info("Loaded %d billing run(s).", len(rows))
        return self.mapper.to_models(rows)

    async def mark_running(
        self, run_id: str, started_at: datetime
    ) -> Optional[BillingRun]:
        """Record that a worker picked a run up.

        Args:
            run_id (str): The run to update.
            started_at (datetime): When it was picked up.

        Returns:
            Optional[BillingRun]: The updated run, or ``None`` when there is no
            such row.
        """
        row = await self._get_row(run_id)
        if row is None:
            self.logger.warning(
                "Cannot mark as running: no billing run found with id %s.",
                run_id,
            )
            return None
        self.logger.info("Billing run %s started at %s.", run_id, started_at)
        row.status = BillingRunStatus.RUNNING.value
        row.started_at = started_at
        await self.session.flush()
        return self.mapper.to_model(row)

    async def mark_finished(
        self,
        run_id: str,
        status: BillingRunStatus,
        finished_at: datetime,
        bill_ids: Optional[List[str]] = None,
        failed_customer_ids: Optional[List[str]] = None,
        error: Optional[str] = None,
    ) -> Optional[BillingRun]:
        """Record what a run managed to do.

        Args:
            run_id (str): The run to update.
            status (BillingRunStatus): The terminal status it reached.
            finished_at (datetime): When it finished.
            bill_ids (Optional[List[str]]): The invoices it wrote.
            failed_customer_ids (Optional[List[str]]): The customers it could
                not bill.
            error (Optional[str]): Why it failed, when it did.

        Returns:
            Optional[BillingRun]: The updated run, or ``None`` when there is no
            such row.

        Notes:
            Both outcome lists are written even when empty, because "billed
            nobody and failed nobody" is a real answer — a period with no
            deliverable work — and leaving the columns null would make it
            indistinguishable from a run that never reported.
        """
        row = await self._get_row(run_id)
        if row is None:
            self.logger.warning(
                "Cannot mark as finished: no billing run found with id %s.",
                run_id,
            )
            return None
        written = list(bill_ids or [])
        failed = list(failed_customer_ids or [])
        row.status = status.value
        row.finished_at = finished_at
        row.bill_ids = written
        row.failed_customer_ids = failed
        row.error_message = error
        await self.session.flush()
        if status is BillingRunStatus.FAILED:
            self.logger.error(
                "Billing run %s failed after writing %d bill(s): %s.",
                run_id,
                len(written),
                error,
            )
        elif failed:
            self.logger.warning(
                "Billing run %s finished %s: %d bill(s) written, %d customer(s) "
                "could not be billed.",
                run_id,
                status.value,
                len(written),
                len(failed),
            )
        else:
            self.logger.info(
                "Billing run %s finished %s with %d bill(s).",
                run_id,
                status.value,
                len(written),
            )
        return self.mapper.to_model(row)
