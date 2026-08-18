from __future__ import annotations

# Standard library imports
from decimal import Decimal
from typing import Dict, List, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator

# First-party imports
from models.configuration.holiday_surcharge import HolidaySurcharge
from models.configuration.pricing_config import PricingConfig
from models.enums import ServiceCategory
from models.schemas.exceptions import (
    MTPricingRulesResponseInvalidBaseRate,
    MTPricingRulesResponseInvalidSurcharges,
)


class PricingRulesResponse(BaseModel):
    """The agency-wide rules an intervention type is priced against.

    Attributes:
        base_hourly_rate_ht (Decimal): The rate a type bills at when it sets
            none of its own.
        weekday_surcharges (Dict[str, Decimal]): Multiplier by weekday, for the
            days that carry one.
        holiday_surcharges (List[HolidaySurcharge]): Fixed dates that carry a
            multiplier.
        vat_rates (Dict[str, Decimal]): The VAT rate each service category is
            billed at.

    Notes:
        **Published so the catalogue screen can show what a rate means.** A
        manager setting an hourly rate needs three things the catalogue itself
        does not hold: what an entry costs when it names no rate of its own,
        what a Sunday multiplies it by, and which VAT rate its category carries.
        Without them the screen shows a number with no context, and "leave
        empty for the agency rate" is advice about a figure the reader cannot
        see.

        **Read-only, and read from the running configuration.** These rules live
        in the configuration file rather than the database — a rate change is a
        commercial decision with an audit trail, not a form somebody fills in —
        so this response restates them rather than offering to set them. The
        screen says as much, because a field that cannot be edited and does not
        explain itself reads as a bug.
    """

    base_hourly_rate_ht: Decimal = Field(
        description="The rate a type bills at when it sets none of its own.",
    )
    weekday_surcharges: Dict[str, Decimal] = Field(
        default_factory=dict, description="Multiplier by weekday."
    )
    holiday_surcharges: List[HolidaySurcharge] = Field(
        default_factory=list, description="Fixed dates carrying a multiplier."
    )
    vat_rates: Dict[str, Decimal] = Field(
        default_factory=dict, description="VAT rate by service category."
    )

    @field_validator("base_hourly_rate_ht", mode="before")
    def validate_base_hourly_rate_ht(
        cls, value: Union[str, int, float, Decimal, None]
    ) -> Decimal:
        """Validates that the agency-wide rate is strictly positive.

        Args:
            value (Union[str, int, float, Decimal, None]): Raw rate.

        Returns:
            Decimal: The validated rate.

        Raises:
            MTPricingRulesResponseInvalidBaseRate: If ``value`` is missing, not
                a number, or not strictly positive.

        Notes:
            A rate of zero would publish "every entry that names no rate is
            free", and the screen would show it as the figure a manager is
            deciding against. The configuration already refuses one. This
            refuses to *restate* one, so a bad value cannot reach the screen
            through a path the configuration did not check.
        """
        if value is None or isinstance(value, bool):
            raise MTPricingRulesResponseInvalidBaseRate(
                f"Invalid base_hourly_rate_ht: {value!r}. Must be a number."
            )
        try:
            rate = Decimal(str(value))
        except (ArithmeticError, ValueError):
            raise MTPricingRulesResponseInvalidBaseRate(
                f"Invalid base_hourly_rate_ht: {value!r}. Must be a number."
            ) from None
        if rate <= 0:
            raise MTPricingRulesResponseInvalidBaseRate(
                f"Invalid base_hourly_rate_ht: {value!r}. Must be positive."
            )
        return rate

    @field_validator("weekday_surcharges", "vat_rates", mode="before")
    def validate_rate_mapping(cls, value: JsonValue) -> JsonValue:
        """Validates that a rate mapping is a mapping.

        Args:
            value (JsonValue): Raw mapping value.

        Returns:
            JsonValue: The value, unchanged, for the field type to parse.

        Raises:
            MTPricingRulesResponseInvalidSurcharges: If ``value`` is neither
                ``None`` nor a mapping.

        Notes:
            An empty mapping is a real state: an agency may surcharge no day of
            the week at all. A list where a mapping is expected is not, and
            would otherwise be reported as a type error naming neither field.
        """
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise MTPricingRulesResponseInvalidSurcharges(
                f"Invalid rate mapping: {value!r}. Must be a mapping."
            )
        return value

    @classmethod
    def from_config(cls, config: PricingConfig) -> PricingRulesResponse:
        """Build the response from the running pricing configuration.

        Args:
            config (PricingConfig): The agency's pricing rules.

        Returns:
            PricingRulesResponse: The published form of those rules.

        Notes:
            The VAT rates are asked of :class:`ServiceCategory` rather than
            listed here. They are the categories' own answer, and a second copy
            would be a second place for the reduced rate on necessity care to
            be wrong.
        """
        return cls(
            base_hourly_rate_ht=config.base_hourly_rate_ht,
            weekday_surcharges={
                day.value: multiplier
                for day, multiplier in config.weekday_surcharges.items()
            },
            holiday_surcharges=list(config.holiday_surcharges),
            vat_rates={
                category.value: category.vat_rate() for category in ServiceCategory
            },
        )
