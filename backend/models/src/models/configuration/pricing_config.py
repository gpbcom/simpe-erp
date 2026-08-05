from __future__ import annotations

# Standard library imports
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Dict, List, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator

# First-party imports
from models.configuration.exceptions import (
    MTPricingConfigInvalidBaseHourlyRate,
    MTPricingConfigInvalidHolidaySurcharges,
    MTPricingConfigInvalidWeekdaySurcharges,
)
from models.configuration.holiday_surcharge import HolidaySurcharge
from models.enums import Weekday


class PricingConfig(BaseModel):
    """The agency-wide pricing rules used to price a quote line.

    Attributes:
        DEFAULT_BASE_HOURLY_RATE_HT (ClassVar[Decimal]): The contractual base
            rate, ``31.905`` EUR per hour excluding tax.
        MAX_SURCHARGE (ClassVar[Decimal]): Upper bound accepted for a weekday
            surcharge ratio.
        base_hourly_rate_ht (Decimal): Default hourly rate excluding tax, in
            EUR. An intervention type may override it; when it does not, this
            is the rate that applies.
        weekday_surcharges (Dict[Weekday, Decimal]): Fractional uplift per
            weekday. Absent weekdays carry no surcharge.
        holiday_surcharges (List[HolidaySurcharge]): Fixed-date holidays that
            carry an uplift.

    Notes:
        Surcharges are **not cumulative**. A date that is both a surcharged
        weekday and a surcharged holiday takes the single largest applicable
        uplift, so 1 January falling on a Sunday bills at +50% rather than at
        +87.5%. Stacking the two would produce a rate no one quoted, and the
        larger of the two is the customer-facing reading of the rules.
    """

    DEFAULT_BASE_HOURLY_RATE_HT: ClassVar[Decimal] = Decimal("31.905")
    MAX_SURCHARGE: ClassVar[Decimal] = Decimal("10")

    base_hourly_rate_ht: Decimal = Field(
        default=DEFAULT_BASE_HOURLY_RATE_HT,
        description="Default hourly rate excluding tax, in EUR.",
    )
    weekday_surcharges: Dict[Weekday, Decimal] = Field(
        default_factory=dict,
        description="Fractional uplift per weekday; 0.25 means +25%.",
    )
    holiday_surcharges: List[HolidaySurcharge] = Field(
        default_factory=list,
        description="Fixed-date holidays carrying an hourly-rate uplift.",
    )

    @field_validator("base_hourly_rate_ht", mode="before")
    def validate_base_hourly_rate_ht(
        cls, value: Union[int, float, str, Decimal, None]
    ) -> Decimal:
        """Validates that ``base_hourly_rate_ht`` is a positive decimal amount.

        Args:
            value (Union[int, float, str, Decimal, None]): Raw rate value.
                ``None`` falls back to :attr:`DEFAULT_BASE_HOURLY_RATE_HT`.

        Returns:
            Decimal: The validated hourly rate.

        Raises:
            MTPricingConfigInvalidBaseHourlyRate: If ``value`` cannot be read
                as a decimal, or is not strictly positive.

        Notes:
            The value is routed through ``str`` before reaching
            :class:`~decimal.Decimal` so a YAML float such as ``31.905`` keeps
            its exact decimal value rather than picking up the binary
            approximation that ``Decimal(31.905)`` would produce.
        """
        if value is None:
            return cls.DEFAULT_BASE_HOURLY_RATE_HT
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):  # noqa: E501
            raise MTPricingConfigInvalidBaseHourlyRate(
                f"Invalid base_hourly_rate_ht: {value!r}. "
                f"Must be a positive decimal amount."
            )
        try:
            coerced = Decimal(str(value))
        except InvalidOperation, ValueError:
            raise MTPricingConfigInvalidBaseHourlyRate(
                f"Invalid base_hourly_rate_ht: {value!r}. "
                f"Must be a positive decimal amount."
            ) from None
        if not coerced.is_finite() or coerced <= 0:
            raise MTPricingConfigInvalidBaseHourlyRate(
                f"Invalid base_hourly_rate_ht: {coerced!r}. Must be strictly positive."
            )
        return coerced

    @field_validator("weekday_surcharges", mode="before")
    def validate_weekday_surcharges(cls, value: JsonValue) -> Dict[Weekday, Decimal]:  # noqa: E501
        """Validates the weekday-surcharge map.

        Args:
            value (JsonValue): Raw mapping of weekday to surcharge ratio.
                ``None`` yields an empty map.

        Returns:
            Dict[Weekday, Decimal]: The validated map, keyed by
            :class:`~models.enums.Weekday`.

        Raises:
            MTPricingConfigInvalidWeekdaySurcharges: If ``value`` is not a
                mapping, if a key is not a known weekday, or if a value is not
                a non-negative decimal ratio.
        """
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise MTPricingConfigInvalidWeekdaySurcharges(
                f"Invalid weekday_surcharges: {value!r}. Must be a mapping or None."
            )
        validated: Dict[Weekday, Decimal] = {}
        for raw_weekday, raw_surcharge in value.items():
            try:
                weekday = Weekday(raw_weekday)
            except ValueError:
                raise MTPricingConfigInvalidWeekdaySurcharges(
                    f"Invalid weekday_surcharges key: {raw_weekday!r}. "
                    f"Must be one of: {', '.join(Weekday.values())}."
                ) from None
            if isinstance(raw_surcharge, bool) or not isinstance(
                raw_surcharge, (int, float, str, Decimal)
            ):
                raise MTPricingConfigInvalidWeekdaySurcharges(
                    f"Invalid weekday_surcharges value for {weekday.value}: "
                    f"{raw_surcharge!r}. Must be a non-negative decimal ratio."
                )
            try:
                surcharge = Decimal(str(raw_surcharge))
            except InvalidOperation, ValueError:
                raise MTPricingConfigInvalidWeekdaySurcharges(
                    f"Invalid weekday_surcharges value for {weekday.value}: "
                    f"{raw_surcharge!r}. Must be a non-negative decimal ratio."
                ) from None
            if not surcharge.is_finite() or surcharge < 0:
                raise MTPricingConfigInvalidWeekdaySurcharges(
                    f"Invalid weekday_surcharges value for {weekday.value}: "
                    f"{surcharge!r}. Must be non-negative."
                )
            if surcharge > cls.MAX_SURCHARGE:
                raise MTPricingConfigInvalidWeekdaySurcharges(
                    f"Invalid weekday_surcharges value for {weekday.value}: "
                    f"{surcharge!r}. Must be at most {cls.MAX_SURCHARGE} "
                    f"(a ratio, not a percentage)."
                )
            validated[weekday] = surcharge
        return validated

    @field_validator("holiday_surcharges", mode="before")
    def validate_holiday_surcharges(cls, value: JsonValue) -> JsonValue:
        """Validates that ``holiday_surcharges`` is a list of holiday entries.

        Args:
            value (JsonValue): Raw list of holiday-surcharge payloads. ``None``
                yields an empty list.

        Returns:
            JsonValue: The list handed back for Pydantic to build into
            :class:`~models.configuration.holiday_surcharge.HolidaySurcharge`
            instances.

        Raises:
            MTPricingConfigInvalidHolidaySurcharges: If ``value`` is neither
                ``None`` nor a list, or if an element is neither a mapping nor
                an already-built holiday.

        Notes:
            The elements are deliberately not coerced here: asserting the shape
            and handing the payload back lets each ``HolidaySurcharge`` raise
            its own field-level exception, which names the offending field
            rather than the whole list.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTPricingConfigInvalidHolidaySurcharges(
                f"Invalid holiday_surcharges: {value!r}. Must be a list or None."
            )
        for entry in value:
            if not isinstance(entry, (HolidaySurcharge, dict)):
                raise MTPricingConfigInvalidHolidaySurcharges(
                    f"Invalid holiday_surcharges entry: {entry!r}. "
                    f"Must be a HolidaySurcharge or a mapping."
                )
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def surcharge_for(self, service_date: date) -> Decimal:
        """Return the largest surcharge applying to a date.

        Args:
            service_date (date): The date the service is delivered on.

        Returns:
            Decimal: The fractional uplift, ``Decimal("0")`` when the date
            carries no surcharge.

        Notes:
            The maximum — not the sum — of the applicable surcharges is
            returned; see the class notes for why.
        """
        applicable = [Decimal("0")]
        weekday = Weekday.from_iso_weekday(service_date.isoweekday())
        weekday_surcharge = self.weekday_surcharges.get(weekday)
        if weekday_surcharge is not None:
            applicable.append(weekday_surcharge)
        for holiday in self.holiday_surcharges:
            if holiday.falls_on(service_date):
                applicable.append(holiday.surcharge)
        return max(applicable)

    def multiplier_for(self, service_date: date) -> Decimal:
        """Return the hourly-rate multiplier applying to a date.

        Args:
            service_date (date): The date the service is delivered on.

        Returns:
            Decimal: ``1 + surcharge``. ``Decimal("1")`` on an ordinary day,
            ``Decimal("1.25")`` on a surcharged Sunday, ``Decimal("1.50")`` on
            Christmas Day or New Year's Day.
        """
        return Decimal("1") + self.surcharge_for(service_date)
