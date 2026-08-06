from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Optional, Tuple, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.quoting.exceptions import (
    MTAggregateInvalidAmount,
    MTAggregateInvalidCount,
    MTAggregateInvalidInterventionTypeId,
    MTAggregateInvalidInterventionTypeName,
    MTAggregateInvalidIsoWeek,
    MTAggregateInvalidIsoYear,
    MTAggregateInvalidWeekStart,
)


class QuoteTypeWeekAggregate(BaseModel):
    """One quote's lines of a given type, summed over one ISO week.

    Attributes:
        MAX_ISO_WEEK (ClassVar[int]): Highest ISO week number a year can hold.
        MONEY_FIELDS (ClassVar[Tuple[str, ...]]): The fields holding an amount.
        intervention_type_id (str): The type these lines share.
        intervention_type_name (str): Its name, copied so the aggregate reads
            without a join.
        iso_year (int): ISO year of the week.
        iso_week (int): ISO week number, ``1..53``.
        week_start_date (date): The Monday of that ISO week.
        line_count (int): How many lines were summed.
        total_minutes (int): Total service time in the week.
        total_ht (Decimal): Total excluding tax.
        vat_amount (Decimal): Total tax.
        total_ttc (Decimal): Total including tax.

    Notes:
        - Both the ISO **year** and the week number are stored. The ISO year
          differs from the calendar year at the boundaries — 29 December 2025
          falls in ISO week 1 of 2026 — so grouping on the week number alone
          would silently merge two weeks a year apart.
        - The type's name is copied rather than looked up. The aggregate is
          persisted with the quote, and a type renamed next year must not change
          what an issued quote says it sold.
        - Totals are sums of the **already-rounded** line amounts, so the weekly
          subtotals on a printed quote add up to its grand total exactly, with no
          residual cent to explain.
    """

    MAX_ISO_WEEK: ClassVar[int] = 53
    MONEY_FIELDS: ClassVar[Tuple[str, ...]] = ("total_ht", "vat_amount", "total_ttc")

    intervention_type_id: str = Field(description="The type these lines share.")
    intervention_type_name: str = Field(description="The type's name.")
    iso_year: int = Field(description="ISO year of the week.")
    iso_week: int = Field(description="ISO week number, 1..53.")
    week_start_date: date = Field(description="The Monday of that ISO week.")
    line_count: int = Field(description="How many lines were summed.")
    total_minutes: int = Field(description="Total service time in the week.")
    total_ht: Decimal = Field(description="Total excluding tax.")
    vat_amount: Decimal = Field(description="Total tax.")
    total_ttc: Decimal = Field(description="Total including tax.")

    @field_validator("intervention_type_id", mode="before")
    def validate_intervention_type_id(cls, value: Optional[str]) -> str:
        """Validates that ``intervention_type_id`` is a non-empty string.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTAggregateInvalidInterventionTypeId: If not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTAggregateInvalidInterventionTypeId(
                f"Invalid intervention_type_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("intervention_type_name", mode="before")
    def validate_intervention_type_name(cls, value: Optional[str]) -> str:
        """Validates that ``intervention_type_name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw name.

        Returns:
            str: The stripped name.

        Raises:
            MTAggregateInvalidInterventionTypeName: If not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTAggregateInvalidInterventionTypeName(
                f"Invalid intervention_type_name: {value!r}. "
                f"Must be a non-empty string."
            )
        return value.strip()

    @field_validator("iso_year", mode="before")
    def validate_iso_year(cls, value: Union[int, str, None]) -> int:
        """Validates that ``iso_year`` is a plausible year.

        Args:
            value (Union[int, str, None]): Raw ISO year.

        Returns:
            int: The validated year.

        Raises:
            MTAggregateInvalidIsoYear: If ``value`` is not an integer year.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTAggregateInvalidIsoYear(
                f"Invalid iso_year: {value!r}. Must be an integer year."
            )
        if not date.min.year <= value <= date.max.year:
            raise MTAggregateInvalidIsoYear(
                f"Invalid iso_year: {value!r}. Must be a representable year."
            )
        return value

    @field_validator("iso_week", mode="before")
    def validate_iso_week(cls, value: Union[int, str, None]) -> int:
        """Validates that ``iso_week`` is within ``1..53``.

        Args:
            value (Union[int, str, None]): Raw ISO week number.

        Returns:
            int: The validated week number.

        Raises:
            MTAggregateInvalidIsoWeek: If ``value`` is not an integer within
                ``1..53``.

        Notes:
            The bound is 53, not 52: a long ISO year genuinely has 53 weeks,
            and rejecting it would make certain years unquotable.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTAggregateInvalidIsoWeek(
                f"Invalid iso_week: {value!r}. "
                f"Must be an integer within 1..{cls.MAX_ISO_WEEK}."
            )
        if not 1 <= value <= cls.MAX_ISO_WEEK:
            raise MTAggregateInvalidIsoWeek(
                f"Invalid iso_week: {value!r}. Must be within 1..{cls.MAX_ISO_WEEK}."
            )
        return value

    @field_validator("week_start_date", mode="before")
    def validate_week_start_date(
        cls, value: Union[str, date, datetime, None]
    ) -> Union[str, date]:
        """Validates that ``week_start_date`` is a date or an ISO string.

        Args:
            value (Union[str, date, datetime, None]): Raw date.

        Returns:
            Union[str, date]: The value handed back for Pydantic to parse.

        Raises:
            MTAggregateInvalidWeekStart: If ``value`` is not date-like.
        """
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTAggregateInvalidWeekStart(
            f"Invalid week_start_date: {value!r}. Must be a date or an ISO string."
        )

    @field_validator("line_count", "total_minutes", mode="before")
    def validate_count(cls, value: Union[int, str, None]) -> int:
        """Validates that a count is a non-negative integer.

        Args:
            value (Union[int, str, None]): Raw count.

        Returns:
            int: The validated count.

        Raises:
            MTAggregateInvalidCount: If ``value`` is not a non-negative integer.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTAggregateInvalidCount(
                f"Invalid count: {value!r}. Must be a non-negative integer."
            )
        if value < 0:
            raise MTAggregateInvalidCount(
                f"Invalid count: {value!r}. Must be non-negative."
            )
        return value

    @field_validator(*MONEY_FIELDS, mode="before")
    def validate_amount(cls, value: Union[int, float, str, Decimal, None]) -> Decimal:
        """Validates that a money field is a non-negative decimal.

        Args:
            value (Union[int, float, str, Decimal, None]): Raw amount.

        Returns:
            Decimal: The amount as a :class:`~decimal.Decimal`.

        Raises:
            MTAggregateInvalidAmount: If ``value`` cannot be read as a decimal
                or is negative.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):  # noqa: E501
            raise MTAggregateInvalidAmount(
                f"Invalid amount: {value!r}. Must be a non-negative decimal."
            )
        try:
            coerced = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise MTAggregateInvalidAmount(
                f"Invalid amount: {value!r}. Must be a non-negative decimal."
            ) from None
        if not coerced.is_finite() or coerced < 0:
            raise MTAggregateInvalidAmount(
                f"Invalid amount: {coerced!r}. Must be non-negative."
            )
        return coerced

    ############################
    # Publicly Exposed Methods #
    ############################

    def sort_key(self) -> Tuple[int, int, str]:
        """Return the ordering an aggregate is displayed in.

        Returns:
            Tuple[int, int, str]: ISO year, ISO week, then the type's name.

        Notes:
            Chronological first, alphabetical within a week — which is how a
            quote reads: week by week, and inside a week by what was sold.
        """
        return (self.iso_year, self.iso_week, self.intervention_type_name)
