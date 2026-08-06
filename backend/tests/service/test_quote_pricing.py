from __future__ import annotations

# Standard library imports
from datetime import date, time
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import MagicMock

# Third-party imports
import pytest

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.configuration.holiday_surcharge import HolidaySurcharge
from models.configuration.pricing_config import PricingConfig
from models.enums import ServiceCategory, Weekday
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from service.quotes.exceptions import MTPricingUnknownInterventionType
from service.quotes.quotes import QuoteService

# 4 August 2026 is a Tuesday; 9 August 2026 is a Sunday.
TUESDAY = date(2026, 8, 4)
SUNDAY = date(2026, 8, 9)
CHRISTMAS = date(2026, 12, 25)
NEW_YEAR = date(2027, 1, 1)
# 1 January 2034 is a Sunday: a holiday and a surcharged weekday at once.
SUNDAY_NEW_YEAR = date(2034, 1, 1)


@pytest.fixture
def pricing_config() -> PricingConfig:
    """Return the agency's contractual pricing rules.

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


@pytest.fixture
def service(pricing_config: PricingConfig) -> QuoteService:
    """Return a quote service wired to the contractual pricing rules.

    Args:
        pricing_config (PricingConfig): The agency's pricing rules.

    Returns:
        QuoteService: The service under test.

    Notes:
        The repositories are stubbed: these tests exercise the pricing
        arithmetic, which reads nothing and writes nothing. Handing them real
        ones would make every rounding assertion depend on a database.
    """
    return QuoteService(quotes=MagicMock(), types=MagicMock(), config=pricing_config)


def _type(
    type_id: str = "type-necessity",
    category: ServiceCategory = ServiceCategory.NECESSITY,
    rate: Optional[Decimal] = None,
) -> InterventionType:
    """Build an intervention type.

    Args:
        type_id (str): The identifier to assign.
        category (ServiceCategory): The VAT category.
        rate (Decimal): Its own hourly rate, or ``None`` for the default.

    Returns:
        InterventionType: The type.
    """
    return InterventionType(
        id=type_id,
        name=f"Service {type_id}",
        code=type_id.upper().replace("-", "_"),
        service_category=category,
        base_hourly_rate_ht=rate,
    )


def _line(
    service_date: date,
    type_id: str = "type-necessity",
    minutes: int = 120,
    category: ServiceCategory = ServiceCategory.NECESSITY,
    name: str = "Service",
) -> QuoteLine:
    """Build a two-hour morning quote line.

    Args:
        service_date (date): The day the service is delivered.
        type_id (str): The intervention type it sells.
        minutes (int): How long it takes.
        name (str): What the service is.
        category (ServiceCategory): Which VAT rate the line is billed at.

    Returns:
        QuoteLine: The unpriced line.
    """
    return QuoteLine(
        name=name,
        intervention_type_id=type_id,
        service_category=category,
        service_date=service_date,
        earliest_start=time(9, 0),
        latest_end=time(13, 0),
        duration_minutes=minutes,
    )


class TestLinePricing:
    """Tests for the contractual pricing table."""

    # ------------------------------------------------------------------ #
    #  The worked cases
    # ------------------------------------------------------------------ #

    def test_two_hours_necessity_on_a_weekday(self, service: QuoteService) -> None:
        """31.905 x 1.00 x 2h = 63.81 HT, 5.5% VAT."""
        priced = service.price_line(_line(TUESDAY), _type())
        assert priced.total_ht == Decimal("63.81")
        assert priced.vat_amount == Decimal("3.51")
        assert priced.total_ttc == Decimal("67.32")

    def test_two_hours_comfort_on_a_sunday(self, service: QuoteService) -> None:
        """31.905 x 1.25 x 2h = 79.76 HT, 20% VAT."""
        priced = service.price_line(
            _line(SUNDAY, type_id="type-comfort", category=ServiceCategory.COMFORT),
            _type("type-comfort", ServiceCategory.COMFORT),
        )
        assert priced.total_ht == Decimal("79.76")
        assert priced.vat_amount == Decimal("15.95")
        assert priced.total_ttc == Decimal("95.71")

    def test_two_hours_necessity_on_new_years_day(self, service: QuoteService) -> None:
        """31.905 x 1.50 x 2h is exactly 95.715 and must round up.

        Notes:
            This is the case that pins ROUND_HALF_UP. Python's default
            banker's rounding would send the half down to 95.71.
        """
        priced = service.price_line(_line(NEW_YEAR), _type())
        assert priced.total_ht == Decimal("95.72")
        assert priced.vat_amount == Decimal("5.26")
        assert priced.total_ttc == Decimal("100.98")

    def test_christmas_day_carries_the_same_surcharge(
        self, service: QuoteService
    ) -> None:
        """Christmas Day bills at +50%, like New Year's Day."""
        priced = service.price_line(_line(CHRISTMAS), _type())
        assert priced.total_ht == Decimal("95.72")

    # ------------------------------------------------------------------ #
    #  Surcharges do not stack
    # ------------------------------------------------------------------ #

    def test_a_holiday_on_a_sunday_takes_the_larger_surcharge(
        self, service: QuoteService
    ) -> None:
        """1 January 2034 is a Sunday and bills at +50%, not +87.5%.

        Notes:
            Stacking would give 31.905 x 1.875 x 2h = 119.64 — a rate nobody
            quoted.
        """
        assert SUNDAY_NEW_YEAR.isoweekday() == Weekday.SUNDAY.iso_weekday()
        priced = service.price_line(_line(SUNDAY_NEW_YEAR), _type())
        assert priced.total_ht == Decimal("95.72")
        assert priced.total_ht != Decimal("119.64")

    # ------------------------------------------------------------------ #
    #  The type's own rate
    # ------------------------------------------------------------------ #

    def test_a_type_without_a_rate_bills_the_agency_default(
        self, service: QuoteService
    ) -> None:
        """A type that sets no rate falls back to 31.905."""
        priced = service.price_line(_line(TUESDAY), _type(rate=None))
        assert priced.hourly_rate_ht == Decimal("31.91")
        assert priced.total_ht == Decimal("63.81")

    def test_a_type_with_its_own_rate_bills_that(self, service: QuoteService) -> None:
        """A type priced at 40.00 bills 40.00, not the default."""
        priced = service.price_line(_line(TUESDAY), _type(rate=Decimal("40.00")))
        assert priced.total_ht == Decimal("80.00")

    def test_the_surcharge_multiplies_the_types_own_rate(
        self, service: QuoteService
    ) -> None:
        """A 40.00 type on a Sunday bills 50.00/h, not 31.905 x 1.25.

        Notes:
            Computing the surcharge off the agency default would make a premium
            type *cheaper* on a Sunday relative to its own weekday price.
        """
        priced = service.price_line(_line(SUNDAY), _type(rate=Decimal("40.00")))
        assert priced.hourly_rate_ht == Decimal("50.00")
        assert priced.total_ht == Decimal("100.00")

    # ------------------------------------------------------------------ #
    #  VAT follows the line's category
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        ("category", "expected_vat"),
        [
            pytest.param(ServiceCategory.NECESSITY, Decimal("3.51"), id="necessity"),
            pytest.param(ServiceCategory.COMFORT, Decimal("12.76"), id="comfort"),
        ],
    )
    def test_vat_follows_the_line(
        self,
        service: QuoteService,
        category: ServiceCategory,
        expected_vat: Decimal,
    ) -> None:
        """The same service is taxed at 5.5% or 20% by the line's category.

        Notes:
            The intervention type is held constant across both cases, so this
            fails if pricing ever reads the category off the catalog entry
            again.
        """
        priced = service.price_line(
            _line(TUESDAY, category=category), _type(category=ServiceCategory.NECESSITY)
        )
        assert priced.total_ht == Decimal("63.81")
        assert priced.vat_amount == expected_vat

    def test_the_catalog_entry_no_longer_decides_the_tax(
        self, service: QuoteService
    ) -> None:
        """**The change this test exists to lock in.**

        Notes:
            The catalog entry says comfort; the line says necessity. The line
            wins, because which it is depends on the customer rather than on
            the service: help with washing under a care plan is billed at the
            reduced rate, and the same hour arranged privately is not.

            The catalog still fixes the *rate*. It no longer fixes the tax.
        """
        priced = service.price_line(
            _line(TUESDAY, category=ServiceCategory.NECESSITY),
            _type(category=ServiceCategory.COMFORT),
        )

        assert priced.vat_amount == Decimal("3.51")

    # ------------------------------------------------------------------ #
    #  Durations
    # ------------------------------------------------------------------ #

    def test_a_fractional_hour_is_exact(self, service: QuoteService) -> None:
        """50 minutes is 5/6 of an hour, which no float represents exactly."""
        priced = service.price_line(_line(TUESDAY, minutes=50), _type())
        # 31.905 * 50/60 = 26.5875 -> 26.59
        assert priced.total_ht == Decimal("26.59")

    def test_the_input_line_is_not_mutated(self, service: QuoteService) -> None:
        """Pricing returns a copy, so a caller's line stays unpriced."""
        line = _line(TUESDAY)
        service.price_line(line, _type())
        assert line.total_ht is None


class TestQuotePricing:
    """Tests for pricing a whole quote and aggregating it."""

    def _quote(self, lines: List[QuoteLine]) -> Quote:
        """Build a draft quote around some lines.

        Args:
            lines (List[QuoteLine]): The lines to carry.

        Returns:
            Quote: The unpriced quote.
        """
        return Quote(reference="Q-2026-001", customer_id="cust-1", lines=lines)

    def _types(self) -> Dict[str, InterventionType]:
        """Return the two types the tests price against.

        Returns:
            Dict[str, InterventionType]: Keyed by identifier.
        """
        return {
            "type-necessity": _type(),
            "type-comfort": _type("type-comfort", ServiceCategory.COMFORT),
        }

    def test_every_line_is_priced(self, service: QuoteService) -> None:
        """A priced quote reports itself as priced."""
        priced = service.price_quote(
            self._quote([_line(TUESDAY), _line(SUNDAY)]), self._types()
        )
        assert priced.is_priced() is True

    def test_an_empty_quote_is_not_priced(self, service: QuoteService) -> None:
        """A quote with no lines must not be sendable for zero euros."""
        priced = service.price_quote(self._quote([]), self._types())
        assert priced.is_priced() is False

    def test_an_unknown_type_is_fatal(self, service: QuoteService) -> None:
        """A line naming a missing type refuses to price.

        Notes:
            Skipping it would produce a quote silently short a line, which is
            worse than one that refuses.
        """
        with pytest.raises(MTPricingUnknownInterventionType):
            service.price_quote(
                self._quote([_line(TUESDAY, type_id="type-gone")]), self._types()
            )

    # ------------------------------------------------------------------ #
    #  Aggregation by type and week
    # ------------------------------------------------------------------ #

    def test_same_type_same_week_collapses_into_one_aggregate(
        self, service: QuoteService
    ) -> None:
        """Two lines of one type in one week are summed together."""
        priced = service.price_quote(
            self._quote([_line(TUESDAY), _line(date(2026, 8, 5))]), self._types()
        )
        assert len(priced.aggregates) == 1
        assert priced.aggregates[0].line_count == 2
        assert priced.aggregates[0].total_minutes == 240

    def test_same_type_across_two_weeks_stays_split(
        self, service: QuoteService
    ) -> None:
        """A week boundary splits the aggregate."""
        priced = service.price_quote(
            self._quote([_line(TUESDAY), _line(date(2026, 8, 11))]), self._types()
        )
        assert len(priced.aggregates) == 2

    def test_two_types_in_one_week_stay_split(self, service: QuoteService) -> None:
        """Each type gets its own weekly line on the quote."""
        priced = service.price_quote(
            self._quote([_line(TUESDAY), _line(TUESDAY, type_id="type-comfort")]),
            self._types(),
        )
        assert len(priced.aggregates) == 2

    def test_the_iso_year_boundary_does_not_merge_two_weeks(
        self, service: QuoteService
    ) -> None:
        """29 Dec 2025 and 5 Jan 2026 are ISO 2026-W01 and 2026-W02.

        Notes:
            Grouping on the week number alone would merge two different weeks,
            and grouping on the calendar year would split one.
        """
        priced = service.price_quote(
            self._quote([_line(date(2025, 12, 29)), _line(date(2026, 1, 5))]),
            self._types(),
        )
        weeks = {(entry.iso_year, entry.iso_week) for entry in priced.aggregates}
        assert weeks == {(2026, 1), (2026, 2)}

    def test_the_week_start_is_the_monday(self, service: QuoteService) -> None:
        """29 December 2025 is itself the Monday of ISO 2026-W01."""
        priced = service.price_quote(
            self._quote([_line(date(2025, 12, 29))]), self._types()
        )
        assert priced.aggregates[0].week_start_date == date(2025, 12, 29)

    def test_aggregates_come_back_in_display_order(self, service: QuoteService) -> None:
        """Chronological, then alphabetical within a week."""
        priced = service.price_quote(
            self._quote(
                [
                    _line(date(2026, 8, 11)),
                    _line(TUESDAY, type_id="type-comfort"),
                    _line(TUESDAY),
                ]
            ),
            self._types(),
        )
        keys = [entry.sort_key() for entry in priced.aggregates]
        assert keys == sorted(keys)

    # ------------------------------------------------------------------ #
    #  Totals reconcile
    # ------------------------------------------------------------------ #

    def test_the_aggregate_totals_sum_to_the_quote_total(
        self, service: QuoteService
    ) -> None:
        """The weekly subtotals add up to the grand total, to the cent.

        Notes:
            This holds because every level sums amounts that were already
            rounded, rather than re-rounding an exact sum.
        """
        priced = service.price_quote(
            self._quote(
                [
                    _line(TUESDAY),
                    _line(
                        SUNDAY, type_id="type-comfort", category=ServiceCategory.COMFORT
                    ),
                    _line(NEW_YEAR),
                    _line(date(2026, 8, 5), minutes=50),
                ]
            ),
            self._types(),
        )
        line_total = sum(line.total_ht for line in priced.lines)
        assert priced.total_ht() == line_total
        assert priced.total_ttc() == priced.total_ht() + priced.total_vat()

    def test_the_totals_match_the_worked_table(self, service: QuoteService) -> None:
        """A three-line quote totals exactly what the table says."""
        priced = service.price_quote(
            self._quote(
                [
                    _line(TUESDAY),
                    _line(
                        SUNDAY, type_id="type-comfort", category=ServiceCategory.COMFORT
                    ),
                    _line(NEW_YEAR),
                ]
            ),
            self._types(),
        )
        # 63.81 + 79.76 + 95.72
        assert priced.total_ht() == Decimal("239.29")
        # 3.51 + 15.95 + 5.26
        assert priced.total_vat() == Decimal("24.72")
        assert priced.total_ttc() == Decimal("264.01")

    def test_an_unpriced_line_is_left_out_of_the_aggregates(
        self, service: QuoteService
    ) -> None:
        """An aggregate never claims to include a line it could not price."""
        aggregates = service.aggregate([_line(TUESDAY)], {"type-necessity": _type()})
        assert aggregates == []
