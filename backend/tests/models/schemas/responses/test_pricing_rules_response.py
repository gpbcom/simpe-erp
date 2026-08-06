from __future__ import annotations

# Standard library imports
from decimal import Decimal
from typing import Union

# Third-party imports
import pytest

# First-party imports
from models.configuration.pricing_config import PricingConfig
from models.enums import ServiceCategory
from models.schemas.exceptions import (
    MTPricingRulesResponseInvalidBaseRate,
    MTPricingRulesResponseInvalidSurcharges,
)
from models.schemas.responses.pricing_rules_response import PricingRulesResponse


class TestPricingRulesResponse:
    """Tests for the rules the catalogue screen prices against."""

    def test_it_restates_the_running_configuration(self) -> None:
        """The ordinary case: what the deployment is actually charging."""
        config = PricingConfig()

        response = PricingRulesResponse.from_config(config)

        assert response.base_hourly_rate_ht == config.base_hourly_rate_ht

    def test_the_vat_rates_are_the_categories_own_answer(self) -> None:
        """**Asked of the enumeration, never listed here.**

        Notes:
            A second copy would be a second place for the reduced rate on
            necessity care to be wrong — and the one that is wrong would be the
            one on screen, while the invoice used the other.
        """
        response = PricingRulesResponse.from_config(PricingConfig())

        for category in ServiceCategory:
            assert response.vat_rates[category.value] == category.vat_rate()

    def test_every_category_is_published(self) -> None:
        """A category missing here renders as a blank VAT rate on screen."""
        response = PricingRulesResponse.from_config(PricingConfig())

        assert set(response.vat_rates) == {c.value for c in ServiceCategory}

    def test_weekday_surcharges_are_keyed_by_the_day_name(self) -> None:
        """The screen labels them, so it needs a name and not an ordinal."""
        config = PricingConfig(weekday_surcharges={"sunday": "1.25"})

        response = PricingRulesResponse.from_config(config)

        assert response.weekday_surcharges == {"sunday": Decimal("1.25")}

    def test_no_surcharges_at_all_is_a_real_state(self) -> None:
        """An agency may surcharge no day and no holiday."""
        response = PricingRulesResponse(base_hourly_rate_ht=Decimal("30"))

        assert response.weekday_surcharges == {}
        assert response.holiday_surcharges == []

    @pytest.mark.parametrize("value", [None, "0", 0, "-5", Decimal("-0.01"), True])
    def test_a_rate_that_is_not_positive_is_refused(
        self, value: Union[str, int, None]
    ) -> None:
        """**A zero would publish "everything inheriting is free".**

        Args:
            value (Union[str, int, None]): The rejected rate.

        Notes:
            The configuration already refuses one. This refuses to *restate*
            one, so a bad value cannot reach the screen through a path the
            configuration did not check — and the screen is where a manager
            decides what to charge against it.
        """
        with pytest.raises(MTPricingRulesResponseInvalidBaseRate):
            PricingRulesResponse(base_hourly_rate_ht=value)

    def test_a_rate_that_is_not_a_number_is_refused(self) -> None:
        """Reported as this model's own error, not a parser's."""
        with pytest.raises(MTPricingRulesResponseInvalidBaseRate):
            PricingRulesResponse(base_hourly_rate_ht="thirty euros")

    @pytest.mark.parametrize("value", [[], "sunday", 5])
    def test_a_malformed_rate_mapping_is_refused(self, value: object) -> None:
        """A list where a mapping is expected names neither field otherwise.

        Args:
            value (object): The rejected mapping.
        """
        with pytest.raises(MTPricingRulesResponseInvalidSurcharges):
            PricingRulesResponse(
                base_hourly_rate_ht=Decimal("30"), weekday_surcharges=value
            )

    def test_a_missing_mapping_becomes_empty(self) -> None:
        """``None`` means "none", which the screen renders as a word."""
        response = PricingRulesResponse(
            base_hourly_rate_ht=Decimal("30"), weekday_surcharges=None
        )

        assert response.weekday_surcharges == {}
