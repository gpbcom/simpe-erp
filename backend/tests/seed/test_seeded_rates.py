from __future__ import annotations

# Standard library imports
from decimal import Decimal

# Third-party imports
import pytest
from seed.dataset import Dataset

# First-party imports
from models.configuration.pricing_config import PricingConfig


class TestSeededRates:
    """Tests that every seeded service bills at the same hourly rate."""

    @pytest.mark.parametrize("code", [entry[0] for entry in Dataset.INTERVENTION_TYPES])
    def test_every_service_bills_at_the_one_rate(self, code: str) -> None:
        """No entry in the seeded catalog costs a different amount.

        Args:
            code (str): The catalog entry under test.

        Notes:
            Parametrised per entry so a failure names the service that drifted,
            rather than reporting that "the catalog" is wrong and leaving
            somebody to find which of eight rows it was.
        """
        assert Dataset().rate(code) == Decimal(Dataset.HOURLY_RATE_HT)

    def test_the_catalog_offers_exactly_one_price(self) -> None:
        """**The invariant, stated as one assertion over the whole catalog.**

        Notes:
            The per-entry test above would still pass if a ninth service were
            added at a different rate, because it only walks the entries that
            exist. This one collapses the catalog to a set of distinct prices
            and insists there is exactly one — so a new entry at a new price
            fails here even though nothing else changed.
        """
        dataset = Dataset()
        distinct = {dataset.rate(code) for code, _, _ in dataset.INTERVENTION_TYPES}

        assert distinct == {Decimal("31.905")}

    def test_the_rate_matches_the_agency_default(self) -> None:
        """A seeded quote costs what it would with no rate named at all.

        Notes:
            Worth pinning rather than leaving as a coincidence. Because the two
            agree, a seeded total is checkable by hand — hours x 31.905, times
            any surcharge — and the only thing that varies between two lines is
            the VAT their categories carry. If somebody changes the agency rate
            in configuration and not here, the arithmetic in the pricing tests
            and in the documentation stops matching what the demo shows.
        """
        assert Decimal(Dataset.HOURLY_RATE_HT) == PricingConfig().base_hourly_rate_ht

    def test_the_rate_survives_the_column_precision(self) -> None:
        """Three decimal places, and the column stores three.

        Notes:
            ``base_hourly_rate_ht`` is ``Numeric(12, 3)``. A rate carrying more
            precision than that would be rounded on the way into the database,
            and the seeded catalog would then disagree with this constant —
            silently, because both figures print as 31,91 € on screen.
        """
        rate = Decimal(Dataset.HOURLY_RATE_HT)

        assert rate == rate.quantize(Decimal("0.001"))

    def test_an_unknown_code_is_still_refused(self) -> None:
        """One shared rate does not turn ``rate_for`` into a constant function.

        Notes:
            It would have been simpler to return the rate without looking the
            code up at all. Then a typo in a seeded quote would name a service
            that does not exist and be priced anyway, and the seeder would
            build a quote line pointing at nothing.
        """
        with pytest.raises(KeyError):
            Dataset().rate("NOPE")
