from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from typing import List, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

# First-party imports
from models.billing.exceptions import (
    MTBillingRunInvalidDate,
    MTBillingRunInvalidError,
    MTBillingRunInvalidId,
    MTBillingRunInvalidIdentifiers,
    MTBillingRunInvalidMoment,
    MTBillingRunInvalidPeriod,
    MTBillingRunInvalidPeriodicity,
    MTBillingRunInvalidStatus,
)
from models.enums import BillingPeriodicity, BillingRunStatus


class BillingRun(BaseModel):
    """One request to bill a period, and what came of it.

    Attributes:
        id (Optional[str]): Identifier, populated on read from the store.
        company_id (str): The agency whose customers are being billed.
        requested_by (Optional[str]): The account that asked for the run.
        status (BillingRunStatus): Where the run has got to.
        reference_date (date): The day the window was resolved from.
        periodicity (BillingPeriodicity): The rule the window came from.
        period_start (date): First day billed.
        period_end (date): Last day billed.
        bill_ids (List[str]): The bills the run wrote.
        failed_customer_ids (List[str]): The customers it could not bill.
        error (Optional[str]): Why the run failed, when it did.
        requested_at (Optional[datetime]): When it was asked for.
        started_at (Optional[datetime]): When a worker picked it up.
        finished_at (Optional[datetime]): When it reached a terminal status.

    Notes:
        - The record is written **before** the work is queued, so the identifier
          a caller is handed back is real even when the broker is unreachable —
          the same reason a planning run is recorded first.
        - Both outcome lists are kept, not just the successes. A partial run is
          only actionable if it says *which* customers went unbilled; a count
          would leave somebody comparing two lists by hand to find them.
        - The window is stored rather than recomputed from ``reference_date`` and
          ``periodicity`` on read. An agency that changes its periodicity between
          the run and the day somebody reads it would otherwise see a run
          claiming to have billed a period it never touched.
    """

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    company_id: str = Field(description="The agency being billed for.")
    requested_by: Optional[str] = Field(
        default=None,
        description="The account that asked for the run.",
    )
    status: BillingRunStatus = Field(
        default=BillingRunStatus.PENDING,
        description="Where the run has got to.",
    )
    reference_date: date = Field(
        description="The day the window was resolved from.",
    )
    periodicity: BillingPeriodicity = Field(
        description="The rule the window came from.",
    )
    period_start: date = Field(description="First day billed.")
    period_end: date = Field(description="Last day billed.")
    bill_ids: List[str] = Field(
        default_factory=list,
        description="The bills the run wrote.",
    )
    failed_customer_ids: List[str] = Field(
        default_factory=list,
        description="The customers it could not bill.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Why the run failed, when it did.",
    )
    requested_at: Optional[datetime] = Field(
        default=None,
        description="When it was asked for.",
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="When a worker picked it up.",
    )
    finished_at: Optional[datetime] = Field(
        default=None,
        description="When it reached a terminal status.",
    )

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("id", "requested_by", mode="before")
    def validate_optional_identifier(cls, value: Optional[str]) -> Optional[str]:
        """Validates that an optional identifier is ``None`` or non-empty.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            Optional[str]: The stripped identifier, or ``None``.

        Raises:
            MTBillingRunInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTBillingRunInvalidId(
                f"Invalid identifier: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("company_id", mode="before")
    def validate_company_id(cls, value: Optional[str]) -> str:
        """Validates that ``company_id`` names the agency being billed for.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTBillingRunInvalidId: If ``value`` is not a non-empty string.

        Notes:
            Required with no default, for the reason the event publisher requires
            one: a run that did not name its agency would bill every agency's
            customers from one manager's button.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTBillingRunInvalidId(
                f"Invalid company_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("status", mode="before")
    def validate_status(
        cls, value: Union[str, BillingRunStatus, None]
    ) -> BillingRunStatus:
        """Validates that ``status`` is a known billing-run status.

        Args:
            value (Union[str, BillingRunStatus, None]): Raw status. ``None``
                falls back to :attr:`BillingRunStatus.PENDING`.

        Returns:
            BillingRunStatus: The coerced status.

        Raises:
            MTBillingRunInvalidStatus: If ``value`` is not a known status.
        """
        if value is None:
            return BillingRunStatus.PENDING
        if isinstance(value, BillingRunStatus):
            return value
        try:
            return BillingRunStatus(value)
        except ValueError:
            raise MTBillingRunInvalidStatus(
                f"Invalid status: {value!r}. Must be one of: "
                f"{', '.join(BillingRunStatus.values())}."
            ) from None

    @field_validator("periodicity", mode="before")
    def validate_periodicity(
        cls, value: Union[str, BillingPeriodicity, None]
    ) -> BillingPeriodicity:
        """Validates that ``periodicity`` names a known billing rule.

        Args:
            value (Union[str, BillingPeriodicity, None]): Raw periodicity.

        Returns:
            BillingPeriodicity: The coerced periodicity.

        Raises:
            MTBillingRunInvalidPeriodicity: If ``value`` is missing or unknown.
        """
        if isinstance(value, BillingPeriodicity):
            return value
        try:
            return BillingPeriodicity(value)
        except ValueError:
            raise MTBillingRunInvalidPeriodicity(
                f"Invalid periodicity: {value!r}. Must be one of: "
                f"{', '.join(BillingPeriodicity.values())}."
            ) from None

    @field_validator("reference_date", "period_start", "period_end", mode="before")
    def validate_date(cls, value: Union[str, date, datetime, None]) -> Union[str, date]:
        """Validates that a date field is date-like.

        Args:
            value (Union[str, date, datetime, None]): Raw date value.

        Returns:
            Union[str, date]: The value handed back for Pydantic to parse.

        Raises:
            MTBillingRunInvalidDate: If ``value`` is not date-like.
        """
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTBillingRunInvalidDate(
            f"Invalid date: {value!r}. Must be a date or an ISO string."
        )

    @field_validator("requested_at", "started_at", "finished_at", mode="before")
    def validate_moment(
        cls, value: Union[str, datetime, None]
    ) -> Union[str, datetime, None]:
        """Validates that a timestamp is datetime-like or ``None``.

        Args:
            value (Union[str, datetime, None]): Raw timestamp.

        Returns:
            Union[str, datetime, None]: The value handed back for Pydantic to
            parse.

        Raises:
            MTBillingRunInvalidMoment: If ``value`` is neither ``None`` nor
                datetime-like.
        """
        if value is None:
            return None
        if isinstance(value, (str, datetime)):
            return value
        raise MTBillingRunInvalidMoment(
            f"Invalid moment: {value!r}. Must be a datetime or an ISO string."
        )

    @field_validator("bill_ids", "failed_customer_ids", mode="before")
    def validate_identifiers(cls, value: JsonValue) -> List[str]:
        """Validates that an outcome list holds non-empty identifiers.

        Args:
            value (JsonValue): Raw list value.

        Returns:
            List[str]: The stripped identifiers, de-duplicated in order.

        Raises:
            MTBillingRunInvalidIdentifiers: If ``value`` is neither ``None`` nor
                a list of non-empty strings.

        Notes:
            De-duplicated because a retry that re-billed nobody must not make
            the run look as though it wrote the same invoice twice.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTBillingRunInvalidIdentifiers(
                f"Invalid identifiers: {value!r}. Must be a list of non-empty strings."
            )
        identifiers: List[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise MTBillingRunInvalidIdentifiers(
                    f"Invalid identifier: {entry!r}. Must be a non-empty string."
                )
            stripped = entry.strip()
            if stripped not in identifiers:
                identifiers.append(stripped)
        return identifiers

    @field_validator("error", mode="before")
    def validate_error(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``error`` is ``None`` or a non-empty message.

        Args:
            value (Optional[str]): Raw message.

        Returns:
            Optional[str]: The stripped message, or ``None``.

        Raises:
            MTBillingRunInvalidError: If ``value`` is neither ``None`` nor a
                non-empty string.

        Notes:
            An empty string is refused rather than kept, because a failed run
            whose reason renders as blank is indistinguishable on screen from one
            that succeeded quietly.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTBillingRunInvalidError(
                f"Invalid error: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @model_validator(mode="after")
    def check_period(self) -> BillingRun:
        """Ensure the billed window runs forwards.

        Returns:
            BillingRun: ``self`` for chaining.

        Raises:
            MTBillingRunInvalidPeriod: If ``period_end`` falls before
                ``period_start``.
        """
        if self.period_end < self.period_start:
            raise MTBillingRunInvalidPeriod(
                f"Invalid period_end: {self.period_end}. "
                f"Must not be before period_start ({self.period_start})."
            )
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_terminal(self) -> bool:
        """Return whether the run has finished.

        Returns:
            bool: ``True`` once no further status change can follow.

        Notes:
            Delegates to the status rather than repeating its rule, so a client
            polling this and a worker deciding whether to publish a completion
            can never disagree about what "finished" means.
        """
        return self.status.is_terminal()

    def bill_count(self) -> int:
        """Return how many invoices the run wrote.

        Returns:
            int: The number of bills produced.
        """
        return len(self.bill_ids)

    def failure_count(self) -> int:
        """Return how many customers the run could not bill.

        Returns:
            int: The number of customers that failed.
        """
        return len(self.failed_customer_ids)
