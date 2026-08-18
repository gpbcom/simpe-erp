from __future__ import annotations

# Standard library imports
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.configuration.exceptions import (
    MTHolidaySurchargeInvalidDay,
    MTHolidaySurchargeInvalidLabel,
    MTHolidaySurchargeInvalidMonth,
    MTHolidaySurchargeInvalidSurcharge,
)


class HolidaySurcharge(BaseModel):
    """A fixed-date holiday that carries an hourly-rate surcharge.

    Attributes:
        MAX_SURCHARGE (ClassVar[Decimal]): Upper bound accepted for a
            surcharge, guarding against a misplaced decimal point in the
            configuration file.
        month (int): Month of the holiday, ``1..12``.
        day (int): Day of the month, ``1..31``.
        surcharge (Decimal): Fractional uplift on the hourly rate, expressed as
            a ratio: ``Decimal("0.50")`` means ``+50%``.
        label (str): Human-readable name of the holiday.

    Notes:
        Only fixed-date holidays are expressible. That covers the two the
        business rules name — Christmas Day and New Year's Day — and makes the
        catalog pure data, so adding another fixed holiday is a configuration
        entry rather than a code change. A moveable feast such as Easter Monday
        would need a different rule type. None is required today.
    """

    MAX_SURCHARGE: ClassVar[Decimal] = Decimal("10")

    month: int = Field(description="Month of the holiday, 1..12.")
    day: int = Field(description="Day of the month, 1..31.")
    surcharge: Decimal = Field(
        description="Fractional uplift on the hourly rate; 0.50 means +50%.",
    )
    label: str = Field(description="Human-readable name of the holiday.")

    @field_validator("month", mode="before")
    def validate_month(cls, value: Union[int, str]) -> int:
        """Validates that ``month`` is an integer within ``1..12``.

        Args:
            value (Union[int, str]): Raw ``month`` value.

        Returns:
            int: The validated month.

        Raises:
            MTHolidaySurchargeInvalidMonth: If ``value`` is not an integer
                within ``1..12``.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTHolidaySurchargeInvalidMonth(
                f"Invalid month: {value!r}. Must be an integer within 1..12."
            )
        if not 1 <= value <= 12:
            raise MTHolidaySurchargeInvalidMonth(
                f"Invalid month: {value!r}. Must be within 1..12."
            )
        return value

    @field_validator("day", mode="before")
    def validate_day(cls, value: Union[int, str]) -> int:
        """Validates that ``day`` is an integer within ``1..31``.

        Args:
            value (Union[int, str]): Raw ``day`` value.

        Returns:
            int: The validated day of the month.

        Raises:
            MTHolidaySurchargeInvalidDay: If ``value`` is not an integer within
                ``1..31``.

        Notes:
            The upper bound is the loosest one that any month allows. Whether
            the day actually exists in the configured month is checked by
            :meth:`falls_on`, which asks the calendar rather than duplicating
            its month-length table here.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTHolidaySurchargeInvalidDay(
                f"Invalid day: {value!r}. Must be an integer within 1..31."
            )
        if not 1 <= value <= 31:
            raise MTHolidaySurchargeInvalidDay(
                f"Invalid day: {value!r}. Must be within 1..31."
            )
        return value

    @field_validator("surcharge", mode="before")
    def validate_surcharge(cls, value: Union[int, float, str, Decimal]) -> Decimal:  # noqa: E501
        """Validates that ``surcharge`` is a non-negative decimal ratio.

        Args:
            value (Union[int, float, str, Decimal]): Raw ``surcharge`` value.

        Returns:
            Decimal: The validated surcharge as a :class:`~decimal.Decimal`.

        Raises:
            MTHolidaySurchargeInvalidSurcharge: If ``value`` cannot be read as
                a decimal, is negative, or exceeds :attr:`MAX_SURCHARGE`.

        Notes:
            A ``float`` input is routed through ``str`` first, so ``0.5``
            becomes ``Decimal("0.5")`` and not the binary approximation
            ``Decimal("0.5000000000000000277...")``. Money never touches a
            float anywhere in the pricing path, and this is the boundary where
            that guarantee is established.
        """
        if isinstance(value, bool):
            raise MTHolidaySurchargeInvalidSurcharge(
                f"Invalid surcharge: {value!r}. Must be a non-negative decimal ratio."
            )
        if not isinstance(value, (int, float, str, Decimal)):
            raise MTHolidaySurchargeInvalidSurcharge(
                f"Invalid surcharge: {value!r}. Must be a non-negative decimal ratio."
            )
        try:
            coerced = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise MTHolidaySurchargeInvalidSurcharge(
                f"Invalid surcharge: {value!r}. Must be a non-negative decimal ratio."
            ) from None
        if not coerced.is_finite():
            raise MTHolidaySurchargeInvalidSurcharge(
                f"Invalid surcharge: {value!r}. Must be a finite decimal ratio."
            )
        if coerced < 0:
            raise MTHolidaySurchargeInvalidSurcharge(
                f"Invalid surcharge: {coerced!r}. Must be non-negative."
            )
        if coerced > cls.MAX_SURCHARGE:
            raise MTHolidaySurchargeInvalidSurcharge(
                f"Invalid surcharge: {coerced!r}. Must be at most "
                f"{cls.MAX_SURCHARGE} (a ratio, not a percentage)."
            )
        return coerced

    @field_validator("label", mode="before")
    def validate_label(cls, value: Optional[str]) -> str:
        """Validates that ``label`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``label`` value.

        Returns:
            str: The stripped label.

        Raises:
            MTHolidaySurchargeInvalidLabel: If ``value`` is not a string, or is
                empty once stripped.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTHolidaySurchargeInvalidLabel(
                f"Invalid label: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    ############################
    # Publicly Exposed Methods #
    ############################

    def falls_on(self, service_date: date) -> bool:
        """Return whether a date is this holiday.

        Args:
            service_date (date): The date to test.

        Returns:
            bool: ``True`` when the date's month and day match this holiday.

        Notes:
            The year is ignored, which is what makes a fixed-date holiday
            recur. A configured day that does not exist in its month (30
            February, say) simply never matches any real date.
        """
        return service_date.month == self.month and service_date.day == self.day  # noqa: E501
