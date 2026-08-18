from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import ClassVar, Optional

# First-party imports
from models.billing.billing_run import BillingRun
from storage.mappers.base_mapper import BaseMapper
from storage.orm.billing.billing_run_row import BillingRunRow


class BillingRunMapper(BaseMapper[BillingRun, BillingRunRow]):
    """Converts between :class:`BillingRun` and its row.

    Attributes:
        HAS_ROW_TIMESTAMPS (ClassVar[bool]): ``False``. The table dates a run by
            what it did rather than by when its row was touched.
        HAS_MODEL_TIMESTAMPS (ClassVar[bool]): ``False``. Likewise on the model.

    Notes:
        - A run carries three timestamps of its own — requested, started,
          finished — and none of them is "when this row was written". Generic
          ``created_at``/``updated_at`` columns beside them would be a fourth
          and fifth answer to a question already asked three times, and the
          planning run's table makes the same choice.
        - The outcome lists are stored as JSON and read back through the model's
          own validator, which de-duplicates them. A retry that re-billed nobody
          therefore cannot make a run look as though it wrote the same invoice
          twice.
    """

    HAS_ROW_TIMESTAMPS: ClassVar[bool] = False
    HAS_MODEL_TIMESTAMPS: ClassVar[bool] = False

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(
            model_class=BillingRun,
            row_class=BillingRunRow,
            logger=logger,
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_model(self, row: BillingRunRow) -> BillingRun:
        """Build a run from a row's columns.

        Args:
            row (BillingRunRow): The row to read.

        Returns:
            BillingRun: The domain model.

        Raises:
            MTInvalidBillingRunException: If a stored value no longer satisfies
                the model's validators.
        """
        self.logger.debug(
            "Building a billing run from row %s (status %s, %s to %s).",
            row.id,
            row.status,
            row.period_start,
            row.period_end,
        )
        return BillingRun(
            id=row.id,
            company_id=row.company_id,
            requested_by=row.requested_by,
            status=row.status,
            reference_date=row.reference_date,
            periodicity=row.periodicity,
            period_start=row.period_start,
            period_end=row.period_end,
            bill_ids=row.bill_ids,
            failed_customer_ids=row.failed_customer_ids,
            error=row.error_message,
            requested_at=self.timestamps.to_utc(row.requested_at),
            started_at=self.timestamps.to_utc(row.started_at),
            finished_at=self.timestamps.to_utc(row.finished_at),
        )

    def _apply_fields(self, row: BillingRunRow, model: BillingRun) -> None:
        """Write a run's fields onto a row.

        Args:
            row (BillingRunRow): The row to write to.
            model (BillingRun): The model carrying the values.

        Notes:
            ``requested_at`` falls back to the row's existing value rather than
            to the clock, so re-recording a run's outcome never rewrites when it
            was asked for.
        """
        self.logger.debug(
            "Applying a billing run onto row %s (status %s, %d bill(s)).",
            row.id,
            model.status.value,
            model.bill_count(),
        )
        row.company_id = model.company_id
        row.requested_by = model.requested_by
        row.status = model.status.value
        row.reference_date = model.reference_date
        row.periodicity = model.periodicity.value
        row.period_start = model.period_start
        row.period_end = model.period_end
        row.bill_ids = list(model.bill_ids)
        row.failed_customer_ids = list(model.failed_customer_ids)
        row.error_message = model.error
        if model.requested_at is not None:
            row.requested_at = model.requested_at
        elif row.requested_at is None:
            row.requested_at = self._utc_now()
        row.started_at = model.started_at
        row.finished_at = model.finished_at
        if model.failed_customer_ids:
            self.logger.warning(
                "Billing run row %s records %d customer(s) that could not be billed.",
                row.id,
                model.failure_count(),
            )
