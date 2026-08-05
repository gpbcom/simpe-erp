from __future__ import annotations

# Standard library imports
from datetime import date
from decimal import Decimal
from typing import Any

# Third-party imports
import pytest

# First-party imports
from models.configuration.exceptions import (
    MTInvalidPricingConfigException,
    MTPricingConfigInvalidBaseHourlyRate,
    MTPricingConfigInvalidHolidaySurcharges,
    MTPricingConfigInvalidWeekdaySurcharges,
)
from models.configuration.holiday_surcharge import HolidaySurcharge
from models.configuration.pricing_config import PricingConfig
from models.enums import Weekday


@pytest.fixture
def business_rules_config() -> PricingConfig:
    """Return a config carrying the agency's contractual pricing rules.

    Returns:
        PricingConfig: 31.905 EUR/h, Sunday +25%, Christmas and New Year +50%.
    """
    return PricingConfig(
        base_hourly_rate_ht=Decimal("31.905"),
        weekday_surcharges={Weekday.SUNDAY: Decimal("0.25")},
        holiday_surcharges=[
            HolidaySurcharge(
                month=12, day=25, surcharge=Decimal("0.50"), label="Christmas Day"
            ),
            HolidaySurcharge(
                month=1, day=1, surcharge=Decimal("0.50"), label="New Year's Day"
            ),
        ],
    )


class TestPricingConfig:
    """Tests for the PricingConfig model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_defaults_carry_the_contractual_base_rate(self) -> None:
        """The default hourly rate is the contractual 31.905 EUR."""
        assert PricingConfig().base_hourly_rate_ht == Decimal("31.905")

    def test_defaults_have_no_surcharges(self) -> None:
        """A bare config surcharges nothing; the rules come from the file."""
        config = PricingConfig()
        assert config.weekday_surcharges == {}
        assert config.holiday_surcharges == []

    def test_base_rate_is_a_decimal(self) -> None:
        """The rate is a Decimal so quote arithmetic never loses cents."""
        assert isinstance(PricingConfig().base_hourly_rate_ht, Decimal)

    def test_a_float_rate_keeps_its_exact_decimal_value(self) -> None:
        """A YAML float is routed through str, not Decimal(float).

        Notes:
            ``Decimal(31.905)`` yields 31.90500000000000113686837721616029739379...
            Going through ``str`` first is what keeps the configured rate exact.
        """
        config = PricingConfig(base_hourly_rate_ht=31.905)
        assert config.base_hourly_rate_ht == Decimal("31.905")

    # ------------------------------------------------------------------ #
    #  base_hourly_rate_ht validation
    # ------------------------------------------------------------------ #

    def test_none_base_rate_falls_back_to_the_default(self) -> None:
        """An explicit None yields the contractual default."""
        assert PricingConfig(base_hourly_rate_ht=None).base_hourly_rate_ht == Decimal(
            "31.905"
        )

    @pytest.mark.parametrize(
        "invalid_rate",
        [
            pytest.param(Decimal("0"), id="Invalid - zero"),
            pytest.param(Decimal("-1"), id="Invalid - negative"),
            pytest.param("not-a-number", id="Invalid - unparsable string"),
            pytest.param([31.905], id="Invalid - list"),
            pytest.param(True, id="Invalid - bool"),
            pytest.param(float("nan"), id="Invalid - NaN"),
            pytest.param(float("inf"), id="Invalid - infinity"),
        ],
    )
    def test_invalid_base_rate_raises(self, invalid_rate: Any) -> None:
        """A non-positive or unparsable rate is rejected."""
        with pytest.raises(MTPricingConfigInvalidBaseHourlyRate):
            PricingConfig(base_hourly_rate_ht=invalid_rate)

    # ------------------------------------------------------------------ #
    #  weekday_surcharges validation
    # ------------------------------------------------------------------ #

    def test_weekday_keys_are_coerced_to_the_enum(self) -> None:
        """A string weekday key becomes a Weekday member."""
        config = PricingConfig(weekday_surcharges={"sunday": "0.25"})
        assert config.weekday_surcharges == {Weekday.SUNDAY: Decimal("0.25")}

    def test_none_weekday_surcharges_yields_an_empty_map(self) -> None:
        """An absent section is an empty map, not an error."""
        assert PricingConfig(weekday_surcharges=None).weekday_surcharges == {}

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param([("sunday", 0.25)], id="Invalid - list not mapping"),
            pytest.param("sunday", id="Invalid - string"),
        ],
    )
    def test_invalid_weekday_surcharges_container_raises(
        self, invalid_value: Any
    ) -> None:
        """A weekday-surcharge section that is not a mapping is rejected."""
        with pytest.raises(MTPricingConfigInvalidWeekdaySurcharges):
            PricingConfig(weekday_surcharges=invalid_value)

    def test_unknown_weekday_key_raises(self) -> None:
        """A key that is not a weekday is rejected, naming the valid set."""
        with pytest.raises(MTPricingConfigInvalidWeekdaySurcharges):
            PricingConfig(weekday_surcharges={"funday": Decimal("0.25")})

    @pytest.mark.parametrize(
        "invalid_surcharge",
        [
            pytest.param(Decimal("-0.1"), id="Invalid - negative"),
            pytest.param("abc", id="Invalid - unparsable"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(Decimal("25"), id="Invalid - percentage not ratio"),
        ],
    )
    def test_invalid_weekday_surcharge_value_raises(
        self, invalid_surcharge: Any
    ) -> None:
        """A surcharge that is not a sane non-negative ratio is rejected."""
        with pytest.raises(MTPricingConfigInvalidWeekdaySurcharges):
            PricingConfig(weekday_surcharges={Weekday.SUNDAY: invalid_surcharge})

    # ------------------------------------------------------------------ #
    #  holiday_surcharges validation
    # ------------------------------------------------------------------ #

    def test_holiday_dicts_are_built_into_models(self) -> None:
        """A mapping entry becomes a HolidaySurcharge."""
        config = PricingConfig(
            holiday_surcharges=[
                {"month": 12, "day": 25, "surcharge": "0.50", "label": "Christmas"}
            ]
        )
        assert config.holiday_surcharges[0].label == "Christmas"

    def test_none_holiday_surcharges_yields_an_empty_list(self) -> None:
        """An absent section is an empty list, not an error."""
        assert PricingConfig(holiday_surcharges=None).holiday_surcharges == []

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param({"month": 12}, id="Invalid - mapping not list"),
            pytest.param("christmas", id="Invalid - string"),
        ],
    )
    def test_invalid_holiday_surcharges_container_raises(
        self, invalid_value: Any
    ) -> None:
        """A holiday section that is not a list is rejected."""
        with pytest.raises(MTPricingConfigInvalidHolidaySurcharges):
            PricingConfig(holiday_surcharges=invalid_value)

    def test_invalid_holiday_entry_raises(self) -> None:
        """A list entry that is neither a mapping nor a holiday is rejected."""
        with pytest.raises(MTPricingConfigInvalidHolidaySurcharges):
            PricingConfig(holiday_surcharges=["christmas"])

    # ------------------------------------------------------------------ #
    #  surcharge_for / multiplier_for
    # ------------------------------------------------------------------ #

    def test_an_ordinary_weekday_carries_no_surcharge(
        self, business_rules_config: PricingConfig
    ) -> None:
        """4 August 2026 is a Tuesday, so the base rate applies unchanged."""
        assert business_rules_config.multiplier_for(date(2026, 8, 4)) == Decimal("1")

    def test_sunday_carries_a_quarter_surcharge(
        self, business_rules_config: PricingConfig
    ) -> None:
        """9 August 2026 is a Sunday, so the rate is uplifted by 25%."""
        assert business_rules_config.multiplier_for(date(2026, 8, 9)) == Decimal("1.25")

    def test_christmas_day_carries_a_half_surcharge(
        self, business_rules_config: PricingConfig
    ) -> None:
        """25 December 2026 is a Friday, and bills at +50%."""
        assert business_rules_config.multiplier_for(date(2026, 12, 25)) == Decimal(
            "1.50"
        )

    def test_new_years_day_carries_a_half_surcharge(
        self, business_rules_config: PricingConfig
    ) -> None:
        """1 January 2027 is a Friday, and bills at +50%."""
        assert business_rules_config.multiplier_for(date(2027, 1, 1)) == Decimal("1.50")

    @pytest.mark.parametrize(
        "overlapping",
        [
            pytest.param(date(2034, 1, 1), id="New Year's Day 2034"),
            pytest.param(date(2040, 1, 1), id="New Year's Day 2040"),
            pytest.param(date(2033, 12, 25), id="Christmas Day 2033"),
            pytest.param(date(2039, 12, 25), id="Christmas Day 2039"),
        ],
    )
    def test_surcharges_are_not_cumulative_on_a_sunday_holiday(
        self, business_rules_config: PricingConfig, overlapping: date
    ) -> None:
        """A holiday falling on a Sunday bills at +50%, not +87.5%.

        Notes:
            This is the load-bearing case for the max-not-sum rule. Stacking
            +25% on +50% would give a multiplier of 1.875 — a rate nobody
            quoted. The dates are asserted to really be Sundays so the test
            cannot quietly stop exercising the overlap.
        """
        assert overlapping.isoweekday() == Weekday.SUNDAY.iso_weekday()
        assert business_rules_config.multiplier_for(overlapping) == Decimal("1.50")
        assert business_rules_config.multiplier_for(overlapping) != Decimal("1.875")

    def test_the_larger_surcharge_wins_when_the_weekday_is_higher(self) -> None:
        """The maximum is taken whichever rule happens to be the larger one."""
        config = PricingConfig(
            weekday_surcharges={Weekday.SUNDAY: Decimal("0.80")},
            holiday_surcharges=[
                HolidaySurcharge(
                    month=1, day=1, surcharge=Decimal("0.50"), label="New Year's Day"
                )
            ],
        )
        # 1 January 2034 is a Sunday.
        assert config.multiplier_for(date(2034, 1, 1)) == Decimal("1.80")

    def test_surcharge_for_returns_zero_on_an_ordinary_day(
        self, business_rules_config: PricingConfig
    ) -> None:
        """An unsurcharged day yields a zero uplift, not None."""
        assert business_rules_config.surcharge_for(date(2026, 8, 4)) == Decimal("0")

    def test_the_holiday_recurs_every_year(
        self, business_rules_config: PricingConfig
    ) -> None:
        """A fixed-date holiday ignores the year."""
        for year in (2026, 2027, 2028, 2029):
            assert business_rules_config.multiplier_for(date(year, 12, 25)) == Decimal(
                "1.50"
            )

    def test_multiplier_is_a_decimal(
        self, business_rules_config: PricingConfig
    ) -> None:
        """The multiplier is a Decimal so it composes with the rate exactly."""
        assert isinstance(
            business_rules_config.multiplier_for(date(2026, 8, 9)), Decimal
        )

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTPricingConfigInvalidBaseHourlyRate,
            MTPricingConfigInvalidHolidaySurcharges,
            MTPricingConfigInvalidWeekdaySurcharges,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidPricingConfigException."""
        assert issubclass(exception_class, MTInvalidPricingConfigException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_model_dump_round_trip(self, business_rules_config: PricingConfig) -> None:
        """A config survives a dump-and-rebuild unchanged."""
        rebuilt = PricingConfig(**business_rules_config.model_dump())
        assert rebuilt.base_hourly_rate_ht == business_rules_config.base_hourly_rate_ht
        assert rebuilt.multiplier_for(date(2034, 1, 1)) == Decimal("1.50")
