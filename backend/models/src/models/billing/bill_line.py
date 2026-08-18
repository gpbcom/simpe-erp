from __future__ import annotations

# Standard library imports
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Optional, Tuple, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator, model_validator

# First-party imports
from models.billing.exceptions import (
    MTBillLineInvalidAmount,
    MTBillLineInvalidDuration,
    MTBillLineInvalidHca,
    MTBillLineInvalidId,
    MTBillLineInvalidName,
    MTBillLineInvalidServiceCategory,
    MTBillLineInvalidServiceDate,
    MTBillLineInvalidVatRate,
    MTBillLineInvalidVisit,
    MTBillLineInvalidWindow,
)
from models.enums import ServiceCategory


class BillLine(BaseModel):
    """One charged visit on an invoice, and what was actually delivered.

    Attributes:
        MAX_DURATION_MINUTES (ClassVar[int]): Longest single service accepted,
            a full day.
        MONEY_FIELDS (ClassVar[Tuple[str, ...]]): The fields holding an amount.
        id (Optional[str]): Identifier, populated on read from the store.
        quote_line_id (str): The quote line this charge came from.
        intervention_id (Optional[str]): The visit that delivered it, when one
            was ever planned.
        name (str): What the service is, as written on the quote.
        service_category (ServiceCategory): What kind of care this is.
        service_date (date): The day the service was sold for.
        day (Optional[date]): The day it was actually delivered.
        start_time (Optional[time]): When the delivered visit began.
        end_time (Optional[time]): When the delivered visit ended.
        hca_full_name (Optional[str]): Who delivered it.
        duration_minutes (int): How long the service takes.
        hourly_rate_ht (Decimal): Rate billed, surcharge included.
        total_ht (Decimal): Line total excluding tax.
        vat_rate (Decimal): The rate the tax was charged at.
        vat_amount (Decimal): Tax on the line.
        total_ttc (Decimal): Line total including tax.

    Notes:
        - **The money is required, where a quote line's is not.** A quote line is
          legitimately unpriced while a quote is being composed. A bill line that
          is not priced must not exist: an invoice with a blank amount column is
          a legal defect, and refusing to build the model is where that is caught
          rather than on a page already in the post.
        - **The amounts are copied from the quote line, never recomputed.** A
          customer is not re-billed for work already quoted, so a rate that has
          moved in the catalogue since must not reach an invoice for work sold
          before it moved.
        - **``vat_rate`` is stored rather than derived from
          ``service_category``.** If the statutory reduced rate changes, a
          reprinted 2026 invoice must still show the 5.5% it was issued at. The
          same argument :class:`~models.quoting.quote_line.QuoteLine` makes for
          storing its money, one field further.
        - ``quote_line_id`` is provenance and is **never printed**. The
          specification is explicit that a bill lists interventions and not
          quotes, so the identifier exists to answer "where did this charge come
          from" in a support conversation, not to appear on the document.
        - ``intervention_id`` is a **snapshot reference, not a foreign key**.
          Re-planning a period deletes and rewrites every intervention in it, so
          a real key would either take the invoice line with it or block the
          replan. The delivered day, hours and assistant are copied here for the
          same reason the visit copies the customer's address.
        - A line with no ``day`` was sold but never placed by a planning run. It
          is still billed: the visit was agreed and delivered whether or not the
          solver ever saw it, and dropping it would silently forgive work the
          agency did.
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
    quote_line_id: str = Field(description="The quote line this charge is for.")
    intervention_id: Optional[str] = Field(
        default=None,
        description="The visit that delivered it, when one was planned.",
    )
    name: str = Field(description="What the service is.")
    service_category: ServiceCategory = Field(
        description="What kind of care this is.",
    )
    service_date: date = Field(description="The day the service was sold for.")
    day: Optional[date] = Field(
        default=None,
        description="The day it was actually delivered.",
    )
    start_time: Optional[time] = Field(
        default=None,
        description="When the delivered visit began.",
    )
    end_time: Optional[time] = Field(
        default=None,
        description="When the delivered visit ended.",
    )
    hca_full_name: Optional[str] = Field(
        default=None,
        description="Who delivered it.",
    )
    duration_minutes: int = Field(description="How long the service takes.")
    hourly_rate_ht: Decimal = Field(
        description="Rate billed, surcharge included.",
    )
    total_ht: Decimal = Field(description="Line total excluding tax.")
    vat_rate: Decimal = Field(description="The rate the tax was charged at.")
    vat_amount: Decimal = Field(description="Tax on the line.")
    total_ttc: Decimal = Field(description="Line total including tax.")

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("id", "intervention_id", mode="before")
    def validate_optional_identifier(cls, value: Optional[str]) -> Optional[str]:  # noqa: E501
        """Validates that an optional identifier is ``None`` or non-empty.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            Optional[str]: The stripped identifier, or ``None``.

        Raises:
            MTBillLineInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTBillLineInvalidId(
                f"Invalid identifier: {value!r}. "  # noqa: E501
                "Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("quote_line_id", mode="before")
    def validate_quote_line_id(cls, value: Optional[str]) -> str:
        """Validates that ``quote_line_id`` is a non-empty string.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTBillLineInvalidId: If ``value`` is not a non-empty string.

        Notes:
            Required, unlike ``intervention_id``. Every charge comes from
            something that was sold. A line naming no origin could not be
            defended if a customer disputed it.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTBillLineInvalidId(
                f"Invalid quote_line_id: {value!r}. "  # noqa: E501
                "Must be a non-empty string."
            )
        return value.strip()

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw name.

        Returns:
            str: The stripped name.

        Raises:
            MTBillLineInvalidName: If ``value`` is not a non-empty string.

        Notes:
            This is the designation column of the invoice, which French law
            requires to describe the service rendered. An empty one would be a
            row of figures against nothing.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTBillLineInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("hca_full_name", mode="before")
    def validate_hca_full_name(cls, value: Optional[str]) -> Optional[str]:
        """Validates that the assistant's name is ``None`` or non-empty.

        Args:
            value (Optional[str]): Raw name.

        Returns:
            Optional[str]: The stripped name, or ``None``.

        Raises:
            MTBillLineInvalidHca: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTBillLineInvalidHca(
                f"Invalid hca_full_name: {value!r}. "  # noqa: E501
                "Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("service_category", mode="before")
    def validate_service_category(
        cls, value: Union[str, ServiceCategory, None]
    ) -> ServiceCategory:
        """Validates that ``service_category`` names a known kind of care.

        Args:
            value (Union[str, ServiceCategory, None]): Raw category.

        Returns:
            ServiceCategory: The coerced category.

        Raises:
            MTBillLineInvalidServiceCategory: If ``value`` is missing or unknown.

        Notes:
            No default, for the reason the quote line has none: it decides which
            statutory rate the line is grouped under in the totals block, and
            guessing it would misstate the tax on the invoice.
        """
        if isinstance(value, ServiceCategory):
            return value
        try:
            return ServiceCategory(value)
        except ValueError:
            raise MTBillLineInvalidServiceCategory(
                f"Invalid service_category: {value!r}. Must be one of: "
                f"{', '.join(ServiceCategory.values())}."
            ) from None

    @field_validator("service_date", mode="before")
    def validate_service_date(
        cls, value: Optional[Union[str, date, datetime]]
    ) -> Union[str, date]:
        """Validates that ``service_date`` is a date or an ISO string.

        Args:
            value (Optional[Union[str, date, datetime]]): Raw day value.

        Returns:
            Union[str, date]: The value handed back for Pydantic to parse.

        Raises:
            MTBillLineInvalidServiceDate: If ``value`` is missing or is not
                date-like.

        Notes:
            Separate from ``day``'s validator rather than shared with it,
            because the two differ on exactly the case that matters: the sold
            day is what decides which period the charge belongs to, so a missing
            one must be refused by the model with its own exception rather than
            left to surface as a generic validation error the API cannot map.
        """
        if value is None:
            raise MTBillLineInvalidServiceDate(
                "Invalid service_date: the day the service was sold for is required."  # noqa: E501
            )
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTBillLineInvalidServiceDate(
            f"Invalid service_date: {value!r}. "  # noqa: E501
            "Must be a date or an ISO string."
        )

    @field_validator("day", mode="before")
    def validate_day(
        cls, value: Optional[Union[str, date, datetime]]
    ) -> Optional[Union[str, date]]:
        """Validates that ``day`` is a date, an ISO string or ``None``.

        Args:
            value (Optional[Union[str, date, datetime]]): Raw day value.

        Returns:
            Optional[Union[str, date]]: The value handed back for Pydantic to parse.

        Raises:
            MTBillLineInvalidServiceDate: If ``value`` is not date-like.

        Notes:
            ``None`` is legitimate here: it is a service the planner never
            placed, which is billed on its sold date alone.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTBillLineInvalidServiceDate(
            f"Invalid day: {value!r}. Must be a date or an ISO string."
        )

    @field_validator("start_time", "end_time", mode="before")
    def validate_clock_time(
        cls, value: Union[str, time, None]
    ) -> Union[str, time, None]:
        """Validates that a clock time is a time, an ISO string or ``None``.

        Args:
            value (Union[str, time, None]): Raw time value.

        Returns:
            Union[str, time, None]: The value handed back for Pydantic to parse.

        Raises:
            MTBillLineInvalidWindow: If ``value`` is not time-like.
        """
        if value is None:
            return None
        if isinstance(value, (str, time)):
            return value
        raise MTBillLineInvalidWindow(
            f"Invalid time: {value!r}. Must be a time or an ISO string."
        )

    @field_validator("duration_minutes", mode="before")
    def validate_duration_minutes(cls, value: Optional[Union[int, str]]) -> int:  # noqa: E501
        """Validates that ``duration_minutes`` is a positive whole duration.

        Args:
            value (Optional[Union[int, str]]): Raw duration, in minutes.

        Returns:
            int: The validated duration.

        Raises:
            MTBillLineInvalidDuration: If ``value`` is not a strictly positive
                integer, or exceeds a full day.

        Notes:
            This is the quantity column of the invoice. A zero would print an
            amount charged for no time at all, which is the shape of an invoice
            a customer refuses to pay.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTBillLineInvalidDuration(
                f"Invalid duration_minutes: {value!r}. "
                f"Must be a strictly positive integer."
            )
        if value <= 0:
            raise MTBillLineInvalidDuration(
                f"Invalid duration_minutes: {value!r}. "  # noqa: E501
                "Must be strictly positive."
            )
        if value > cls.MAX_DURATION_MINUTES:
            raise MTBillLineInvalidDuration(
                f"Invalid duration_minutes: {value!r}. "
                f"Must be at most {cls.MAX_DURATION_MINUTES}."
            )
        return value

    @field_validator(*MONEY_FIELDS, mode="before")
    def validate_amount(
        cls, value: Optional[Union[int, float, str, Decimal]]
    ) -> Decimal:  # noqa: E501
        """Validates that a money field is a non-negative decimal.

        Args:
            value (Optional[Union[int, float, str, Decimal]]): Raw amount.

        Returns:
            Decimal: The amount as a :class:`~decimal.Decimal`.

        Raises:
            MTBillLineInvalidAmount: If ``value`` is missing, cannot be read as
                a decimal, or is negative.

        Notes:
            - ``None`` is refused, which is the one place this differs from the
              quote line: a bill line has no unpriced state.
            - Routed through ``str`` before reaching :class:`~decimal.Decimal`,
              so a JSON float keeps its exact value instead of the binary
              approximation. Money never touches a float in this application.
        """
        if value is None:
            raise MTBillLineInvalidAmount(
                "Invalid amount: an amount is required on a bill line."
            )
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):  # noqa: E501
            raise MTBillLineInvalidAmount(
                f"Invalid amount: {value!r}. Must be a non-negative decimal."
            )
        try:
            coerced = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise MTBillLineInvalidAmount(
                f"Invalid amount: {value!r}. Must be a non-negative decimal."
            ) from None
        if not coerced.is_finite() or coerced < 0:
            raise MTBillLineInvalidAmount(
                f"Invalid amount: {coerced!r}. Must be non-negative."
            )
        return coerced

    @field_validator("vat_rate", mode="before")
    def validate_vat_rate(
        cls, value: Optional[Union[int, float, str, Decimal]]
    ) -> Decimal:  # noqa: E501
        """Validates that ``vat_rate`` is a proportion between zero and one.

        Args:
            value (Optional[Union[int, float, str, Decimal]]): Raw rate.

        Returns:
            Decimal: The rate as a :class:`~decimal.Decimal`.

        Raises:
            MTBillLineInvalidVatRate: If ``value`` is missing, unreadable, or
                outside ``0..1``.

        Notes:
            A proportion, not a percentage: ``Decimal("0.055")`` and never
            ``5.5``. The two are indistinguishable to a reader of the stored row
            but differ by a factor of a hundred on the printed page, so the
            range check is what makes the unit unambiguous.
        """
        if value is None:
            raise MTBillLineInvalidVatRate(
                "Invalid vat_rate: a rate is required on a bill line."
            )
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):  # noqa: E501
            raise MTBillLineInvalidVatRate(
                f"Invalid vat_rate: {value!r}. Must be a decimal in 0..1."
            )
        try:
            coerced = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise MTBillLineInvalidVatRate(
                f"Invalid vat_rate: {value!r}. Must be a decimal in 0..1."
            ) from None
        if not coerced.is_finite() or not Decimal(0) <= coerced <= Decimal(1):
            raise MTBillLineInvalidVatRate(
                f"Invalid vat_rate: {coerced!r}. "
                "Must be a proportion in 0..1, "
                f"not a percentage."
            )
        return coerced

    @model_validator(mode="after")
    def check_visit(self) -> BillLine:
        """Ensure a delivered visit is recorded whole and runs forwards.

        Returns:
            BillLine: ``self`` for chaining.

        Raises:
            MTBillLineInvalidVisit: If the day and the times are not all present
                or all absent.
            MTBillLineInvalidWindow: If the visit ends before it starts.

        Notes:
            A visit has a day, a start and an end, or it has none of them. Half a
            visit would print a date with no hours beside it, and the reader
            could not tell a service the planner never placed from one whose
            times were lost in transit.
        """
        recorded = (self.day, self.start_time, self.end_time)
        if any(part is not None for part in recorded) and not all(
            part is not None for part in recorded
        ):
            raise MTBillLineInvalidVisit(
                f"Invalid visit: day={self.day!r}, "  # noqa: E501
                f"start_time={self.start_time!r}, "  # noqa: E501
                f"end_time={self.end_time!r}. "
                "Must all be set, or none of them."  # noqa: E501
            )
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise MTBillLineInvalidWindow(
                f"Invalid end_time: {self.end_time}. "
                f"Must be after start_time ({self.start_time})."
            )
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def duration_hours(self) -> Decimal:
        """Return the duration as an exact fraction of an hour.

        Returns:
            Decimal: The duration in hours.

        Notes:
            A :class:`~decimal.Decimal` rather than a float, because it is the
            quantity printed beside a rate: ``90 / 60`` as a float is ``1.5``
            exactly, but ``50 / 60`` is not, and the error would reach the
            invoice.
        """
        return Decimal(self.duration_minutes) / Decimal(60)

    def was_delivered(self) -> bool:
        """Return whether a planned visit was recorded against this charge.

        Returns:
            bool: ``True`` when the delivered day and times are known.

        Notes:
            What the renderer asks before printing the hours and the assistant.
            A charge with no visit is still billed — it was sold and delivered
            whether or not a planning run ever placed it — so this decides how
            much detail the row carries, never whether the row exists.
        """
        return self.day is not None
