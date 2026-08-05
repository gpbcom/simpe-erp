from __future__ import annotations

# Standard library imports
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Optional, Tuple, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator, model_validator

# First-party imports
from models.quoting.exceptions import (
    MTQuoteLineInvalidAmount,
    MTQuoteLineInvalidDuration,
    MTQuoteLineInvalidId,
    MTQuoteLineInvalidInterventionTypeId,
    MTQuoteLineInvalidName,
    MTQuoteLineInvalidServiceDate,
    MTQuoteLineInvalidWindow,
    MTQuoteLineWindowTooShort,
)


class QuoteLine(BaseModel):
    """One priced service on a quote, and the intervention it will become.

    Attributes:
        MAX_DURATION_MINUTES (ClassVar[int]): Longest single service accepted,
            a full day.
        MONEY_FIELDS (ClassVar[Tuple[str, ...]]): The fields holding an amount.
        id (Optional[str]): Identifier, populated on read from the store.
        name (str): What the service is, shown on the quote and carried onto
            the scheduled intervention.
        intervention_type_id (str): The catalog entry that fixes the rate and
            the VAT category.
        service_date (date): The day the service is delivered.
        earliest_start (time): Earliest the service may begin.
        latest_end (time): Latest the service may finish.
        duration_minutes (int): How long the service takes.
        hourly_rate_ht (Optional[Decimal]): Rate actually billed, surcharge
            included. Filled in by pricing.
        total_ht (Optional[Decimal]): Line total excluding tax.
        vat_amount (Optional[Decimal]): Tax on the line.
        total_ttc (Optional[Decimal]): Line total including tax.

    Notes:
        - The line carries a **window** and a **duration**, not a fixed start.
          The customer agrees that two hours of care happen on Tuesday morning;
          which two hours is what the planner decides, along with who delivers
          them. Pinning an exact start here would leave the solver nothing to
          optimise and make most quotes unschedulable.
        - The four money fields are ``None`` until the quote is priced, and are
          **stored** once computed rather than recalculated on read. An issued
          quote must reprint identically even after the intervention type is
          repriced — a customer is never re-billed for work already quoted.
    """

    MAX_DURATION_MINUTES: ClassVar[int] = 24 * 60
    MONEY_FIELDS: ClassVar[Tuple[str, ...]] = (
        "hourly_rate_ht",
        "total_ht",
        "vat_amount",
        "total_ttc",
    )

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    name: str = Field(description="What the service is.")
    intervention_type_id: str = Field(
        description="The catalog entry fixing the rate and the VAT category.",
    )
    service_date: date = Field(description="The day the service is delivered.")
    earliest_start: time = Field(description="Earliest the service may begin.")
    latest_end: time = Field(description="Latest the service may finish.")
    duration_minutes: int = Field(description="How long the service takes.")
    hourly_rate_ht: Optional[Decimal] = Field(
        default=None,
        description="Rate actually billed, surcharge included.",
    )
    total_ht: Optional[Decimal] = Field(
        default=None,
        description="Line total excluding tax.",
    )
    vat_amount: Optional[Decimal] = Field(default=None, description="Tax on the line.")
    total_ttc: Optional[Decimal] = Field(
        default=None,
        description="Line total including tax.",
    )

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``id`` value.

        Returns:
            Optional[str]: The identifier, or ``None``.

        Raises:
            MTQuoteLineInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteLineInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The stripped name.

        Raises:
            MTQuoteLineInvalidName: If ``value`` is not a non-empty string.

        Notes:
            Required because it travels: the scheduled intervention shows this
            text, so an assistant reads "Toilette matin" on their day rather
            than an identifier.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteLineInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("intervention_type_id", mode="before")
    def validate_intervention_type_id(cls, value: Optional[str]) -> str:
        """Validates that ``intervention_type_id`` is a non-empty string.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTQuoteLineInvalidInterventionTypeId: If ``value`` is not a
                non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteLineInvalidInterventionTypeId(
                f"Invalid intervention_type_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("service_date", mode="before")
    def validate_service_date(
        cls, value: Union[str, date, datetime, None]
    ) -> Union[str, date]:
        """Validates that ``service_date`` is a date or an ISO string.

        Args:
            value (Union[str, date, datetime, None]): Raw date value.

        Returns:
            Union[str, date]: The value handed back for Pydantic to parse.

        Raises:
            MTQuoteLineInvalidServiceDate: If ``value`` is not date-like.
        """
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTQuoteLineInvalidServiceDate(
            f"Invalid service_date: {value!r}. Must be a date or an ISO string."
        )

    @field_validator("earliest_start", "latest_end", mode="before")
    def validate_window_bound(cls, value: Union[str, time, None]) -> Union[str, time]:
        """Validates that a window bound is a time or an ISO string.

        Args:
            value (Union[str, time, None]): Raw time value.

        Returns:
            Union[str, time]: The value handed back for Pydantic to parse.

        Raises:
            MTQuoteLineInvalidWindow: If ``value`` is not time-like.
        """
        if isinstance(value, (str, time)):
            return value
        raise MTQuoteLineInvalidWindow(
            f"Invalid window bound: {value!r}. Must be a time or an ISO string."
        )

    @field_validator("duration_minutes", mode="before")
    def validate_duration_minutes(cls, value: Union[int, str, None]) -> int:
        """Validates that ``duration_minutes`` is a positive whole duration.

        Args:
            value (Union[int, str, None]): Raw duration, in minutes.

        Returns:
            int: The validated duration.

        Raises:
            MTQuoteLineInvalidDuration: If ``value`` is not a strictly positive
                integer, or exceeds a full day.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTQuoteLineInvalidDuration(
                f"Invalid duration_minutes: {value!r}. "
                f"Must be a strictly positive integer."
            )
        if value <= 0:
            raise MTQuoteLineInvalidDuration(
                f"Invalid duration_minutes: {value!r}. Must be strictly positive."
            )
        if value > cls.MAX_DURATION_MINUTES:
            raise MTQuoteLineInvalidDuration(
                f"Invalid duration_minutes: {value!r}. "
                f"Must be at most {cls.MAX_DURATION_MINUTES}."
            )
        return value

    @field_validator(*MONEY_FIELDS, mode="before")
    def validate_amount(
        cls, value: Union[int, float, str, Decimal, None]
    ) -> Optional[Decimal]:
        """Validates that a money field is ``None`` or a non-negative decimal.

        Args:
            value (Union[int, float, str, Decimal, None]): Raw amount.

        Returns:
            Optional[Decimal]: The amount as a :class:`~decimal.Decimal`, or
            ``None`` while the line is unpriced.

        Raises:
            MTQuoteLineInvalidAmount: If ``value`` cannot be read as a decimal
                or is negative.

        Notes:
            Routed through ``str`` before reaching :class:`~decimal.Decimal`,
            so a JSON float keeps its exact value instead of the binary
            approximation. Money never touches a float in this application.
        """
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
            raise MTQuoteLineInvalidAmount(
                f"Invalid amount: {value!r}. Must be a non-negative decimal or None."
            )
        try:
            coerced = Decimal(str(value))
        except InvalidOperation, ValueError:
            raise MTQuoteLineInvalidAmount(
                f"Invalid amount: {value!r}. Must be a non-negative decimal or None."
            ) from None
        if not coerced.is_finite() or coerced < 0:
            raise MTQuoteLineInvalidAmount(
                f"Invalid amount: {coerced!r}. Must be non-negative."
            )
        return coerced

    @model_validator(mode="after")
    def check_window(self) -> QuoteLine:
        """Ensure the window can actually contain the service.

        Returns:
            QuoteLine: ``self`` for chaining.

        Raises:
            MTQuoteLineInvalidWindow: If the window does not run forwards.
            MTQuoteLineWindowTooShort: If it is narrower than the duration.

        Notes:
            Caught here rather than left to the solver. A two-hour service in a
            one-hour window is unschedulable, and discovering that as an
            unexplained "unassigned" in a planning run is far worse than being
            told at the moment the line is written.
        """
        if self.latest_end <= self.earliest_start:
            raise MTQuoteLineInvalidWindow(
                f"Invalid latest_end: {self.latest_end}. "
                f"Must be after earliest_start ({self.earliest_start})."
            )
        window_minutes = self._window_minutes()
        if window_minutes < self.duration_minutes:
            raise MTQuoteLineWindowTooShort(
                f"The window {self.earliest_start}-{self.latest_end} is "
                f"{window_minutes} minutes, which cannot contain a "
                f"{self.duration_minutes}-minute service."
            )
        return self

    ############################
    # Internal Helpers Methods #
    ############################

    def _window_minutes(self) -> int:
        """Return how wide the delivery window is.

        Returns:
            int: The window width in minutes.
        """
        start = self.earliest_start.hour * 60 + self.earliest_start.minute
        end = self.latest_end.hour * 60 + self.latest_end.minute
        return end - start

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_priced(self) -> bool:
        """Return whether the line carries its computed amounts.

        Returns:
            bool: ``True`` when every money field is set.
        """
        return all(getattr(self, field) is not None for field in self.MONEY_FIELDS)

    def duration_hours(self) -> Decimal:
        """Return the duration as an exact fraction of an hour.

        Returns:
            Decimal: The duration in hours.

        Notes:
            A :class:`~decimal.Decimal` rather than a float, because it is
            multiplied by a rate: ``90 / 60`` as a float is ``1.5`` exactly,
            but ``50 / 60`` is not, and the error would reach the invoice.
        """
        return Decimal(self.duration_minutes) / Decimal(60)
