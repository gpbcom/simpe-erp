from __future__ import annotations

# Standard library imports
from datetime import date, time
from decimal import Decimal
from typing import List, Optional
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.configuration.pricing_config import PricingConfig
from models.enums import QuoteStatus, ServiceCategory
from models.quoting.exceptions import MTQuoteInvalidInterruption
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from service.quotes.quotes import QuoteService

WEEK_ONE = date(2026, 9, 1)
WEEK_TWO = date(2026, 9, 8)
WEEK_THREE = date(2026, 9, 15)


def _type() -> InterventionType:
    """Build the catalog entry every line here sells.

    Returns:
        InterventionType: The entry.
    """
    return InterventionType(
        id="type-1",
        name="Aide a la toilette",
        code="TOI",
        service_category=ServiceCategory.NECESSITY,
        base_hourly_rate_ht=Decimal("31.905"),
        is_active=True,
    )


def _line(service_date: date) -> QuoteLine:
    """Build a two-hour morning line.

    Args:
        service_date (date): The day it is delivered.

    Returns:
        QuoteLine: The unpriced line.
    """
    return QuoteLine(
        name="Toilette matin",
        intervention_type_id="type-1",
        service_category=ServiceCategory.NECESSITY,
        service_date=service_date,
        earliest_start=time(9, 0),
        latest_end=time(13, 0),
        duration_minutes=120,
    )


def _quote(days: List[date], interrupted: Optional[date] = None) -> Quote:
    """Build an accepted quote covering some days.

    Args:
        days (List[date]): The service dates.
        interrupted (Optional[date]): The last day it runs, if any.

    Returns:
        Quote: The quote.
    """
    return Quote(
        company_id="company-1",
        id="quote-1",
        reference="DEV-2026-001",
        customer_id="customer-1",
        status=QuoteStatus.ACCEPTED,
        issued_on=date(2026, 8, 20),
        valid_until=date(2026, 9, 20),
        interrupted_on=interrupted,
        lines=[_line(day) for day in days],
    )


@pytest.fixture
def service() -> QuoteService:
    """Return a quote service over stand-in repositories.

    Returns:
        QuoteService: The service under test.
    """
    quotes = AsyncMock()
    types = AsyncMock()
    types.get_many.return_value = {"type-1": _type()}
    return QuoteService(
        quotes=quotes,
        types=types,
        config=PricingConfig(),
        teams=AsyncMock(),
        customers=AsyncMock(),
    )


class TestEffectiveLines:
    """Tests for which of a quote's lines still count."""

    def test_an_uninterrupted_quote_delivers_everything(self) -> None:
        """The ordinary case."""
        assert len(_quote([WEEK_ONE, WEEK_TWO, WEEK_THREE]).effective_lines()) == 3

    def test_the_last_day_is_delivered(self) -> None:
        """**Inclusive, and the difference is a visit somebody expects.**

        Notes:
            A family cancelling "from the 15th" means the 15th is the last
            visit. Reading the date as the first cancelled day takes away a
            visit that was arranged, and nothing on screen would say where it
            went.
        """
        quote = _quote([WEEK_ONE, WEEK_TWO, WEEK_THREE], interrupted=WEEK_TWO)

        assert [line.service_date for line in quote.effective_lines()] == [
            WEEK_ONE,
            WEEK_TWO,
        ]

    def test_the_cancelled_lines_are_kept(self) -> None:
        """**Shortening does not erase what was agreed.**

        Notes:
            A family asking why the invoice came in under the quote they signed
            needs to see both figures. Deleting the cancelled visits would
            leave nothing to answer with.
        """
        quote = _quote([WEEK_ONE, WEEK_TWO, WEEK_THREE], interrupted=WEEK_ONE)

        assert len(quote.lines) == 3
        assert len(quote.effective_lines()) == 1

    def test_an_interruption_after_the_last_service_changes_nothing(self) -> None:
        """A closing date the work already fits inside is a real thing to record."""
        quote = _quote([WEEK_ONE, WEEK_TWO], interrupted=date(2026, 12, 31))

        assert len(quote.effective_lines()) == 2

    def test_an_interruption_before_the_first_service_is_refused(self) -> None:
        """It would leave an accepted quote delivering nothing.

        Notes:
            A quote that costs nothing, delivers nothing and still reads as
            live is worse than a rejected one — rejection says what happened.
        """
        with pytest.raises(MTQuoteInvalidInterruption):
            _quote([WEEK_TWO, WEEK_THREE], interrupted=WEEK_ONE)

    def test_an_interruption_before_the_quote_was_issued_is_refused(self) -> None:
        """An arrangement cannot end before it was offered."""
        with pytest.raises(MTQuoteInvalidInterruption):
            Quote(
                company_id="company-1",
                reference="DEV-1",
                customer_id="customer-1",
                issued_on=date(2026, 8, 20),
                interrupted_on=date(2026, 8, 1),
                lines=[_line(date(2026, 7, 1))],
            )


class TestInterruptionPricing:
    """Tests that a shortened quote costs what it still delivers."""

    def test_the_total_drops_to_the_delivered_work(self, service: QuoteService) -> None:
        """**The requirement: shorten the quote, adapt the price.**

        Notes:
            Three identical weekly visits, cut to one. The total is asserted as
            a third of the full one rather than against a figure, so it holds
            when the agency rate changes.
        """
        full = service.price_quote(
            _quote([WEEK_ONE, WEEK_TWO, WEEK_THREE]), {"type-1": _type()}
        )
        shortened = service.price_quote(
            _quote([WEEK_ONE, WEEK_TWO, WEEK_THREE], interrupted=WEEK_ONE),
            {"type-1": _type()},
        )

        assert shortened.total_ttc() < full.total_ttc()
        assert shortened.total_ttc() == full.total_ttc() / 3

    def test_a_cancelled_line_keeps_its_own_amounts(
        self, service: QuoteService
    ) -> None:
        """**So an interruption ends the tail, not the whole arrangement.**

        Notes:
            The dropped lines are priced and then left out of the totals rather
            than left unpriced. An unpriced line on an accepted quote trips
            ``is_priced``, which would make the quote unschedulable — and the
            planner would stop producing the visits *before* the interruption
            too, cancelling work the family is expecting this week.
        """
        priced = service.price_quote(
            _quote([WEEK_ONE, WEEK_TWO], interrupted=WEEK_ONE), {"type-1": _type()}
        )

        assert priced.lines[-1].total_ttc is not None
        assert priced.is_priced() is True
        assert priced.is_schedulable() is True

    def test_the_totals_count_only_the_delivered_lines(
        self, service: QuoteService
    ) -> None:
        """The aggregates are the totals, so they are what has to shrink."""
        priced = service.price_quote(
            _quote([WEEK_ONE, WEEK_TWO, WEEK_THREE], interrupted=WEEK_TWO),
            {"type-1": _type()},
        )

        assert sum(aggregate.line_count for aggregate in priced.aggregates) == 2

    async def test_interrupting_stores_the_new_total(
        self, service: QuoteService
    ) -> None:
        """Repricing happens on the way in, not on every read.

        Notes:
            An issued quote must reprint identically, so amounts are stored. A
            total recomputed on read would drift the first time the catalog
            changed; interrupting is the deliberate act that makes a new total
            correct, so it is the moment to write one.
        """
        service.quotes.get.return_value = _quote([WEEK_ONE, WEEK_TWO, WEEK_THREE])
        service.quotes.update.side_effect = lambda quote: quote

        result = await service.interrupt("quote-1", WEEK_ONE)

        assert result.interrupted_on == WEEK_ONE
        assert sum(aggregate.line_count for aggregate in result.aggregates) == 1
        service.quotes.update.assert_awaited_once()

    async def test_interrupting_twice_is_the_later_answer(
        self, service: QuoteService
    ) -> None:
        """A family extending their notice moves the end date out again.

        Notes:
            The second call reprices from the *stored* lines, all of which are
            still there — which is only possible because the first interruption
            kept them. Deleting them would make an extension impossible to
            express without rewriting the quote.
        """
        service.quotes.get.return_value = _quote(
            [WEEK_ONE, WEEK_TWO, WEEK_THREE], interrupted=WEEK_ONE
        )
        service.quotes.update.side_effect = lambda quote: quote

        result = await service.interrupt("quote-1", WEEK_THREE)

        assert result.interrupted_on == WEEK_THREE
        assert sum(aggregate.line_count for aggregate in result.aggregates) == 3
