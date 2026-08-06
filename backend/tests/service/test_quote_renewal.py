from __future__ import annotations

# Standard library imports
from datetime import date, time
from decimal import Decimal

from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.configuration.pricing_config import PricingConfig
from models.enums import QuoteStatus, ServiceCategory
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from service.quotes.quotes import QuoteService

FIRST_SERVICE = date(2026, 9, 1)
LAST_SERVICE = date(2026, 9, 28)
EXPIRED_ON = date(2026, 9, 30)
TODAY = date(2026, 10, 1)


def _type(rate: str = "31.905") -> InterventionType:
    """Build the catalog entry every line here sells.

    Args:
        rate (str): The hourly rate it bills at.

    Returns:
        InterventionType: The entry.
    """
    return InterventionType(
        id="type-1",
        name="Aide a la toilette",
        code="TOI",
        service_category=ServiceCategory.NECESSITY,
        base_hourly_rate_ht=Decimal(rate),
        is_active=True,
    )


def _line(service_date: date) -> QuoteLine:
    """Build a two-hour morning line.

    Args:
        service_date (date): The day it is delivered.

    Returns:
        QuoteLine: The line, priced as a stored one would be.
    """
    return QuoteLine(
        name="Toilette matin",
        intervention_type_id="type-1",
        service_category=ServiceCategory.NECESSITY,
        service_date=service_date,
        earliest_start=time(9, 0),
        latest_end=time(13, 0),
        duration_minutes=120,
        hourly_rate_ht=Decimal("31.91"),
        total_ht=Decimal("63.81"),
        vat_amount=Decimal("3.51"),
        total_ttc=Decimal("67.32"),
    )


def _parent(**overrides: object) -> Quote:
    """Build an expired, accepted, auto-renewing arrangement.

    Args:
        **overrides: Fields to change.

    Returns:
        Quote: The parent quote.
    """
    fields = {
        "id": "quote-1",
        "reference": "DEV-2026-001",
        "customer_id": "customer-1",
        "status": QuoteStatus.ACCEPTED,
        "issued_on": date(2026, 8, 20),
        "valid_until": EXPIRED_ON,
        "auto_renew": True,
        "authored_by": "user-1",
        "lines": [_line(FIRST_SERVICE), _line(LAST_SERVICE)],
    }
    fields.update(overrides)
    return Quote(**fields)


@pytest.fixture
def service() -> QuoteService:
    """Return a quote service over stand-in repositories.

    Returns:
        QuoteService: The service under test, storing whatever it creates.
    """
    quotes = AsyncMock()
    quotes.has_successor.return_value = False
    quotes.create.side_effect = lambda quote: quote
    types = AsyncMock()
    types.get_many.return_value = {"type-1": _type()}
    return QuoteService(quotes=quotes, types=types, config=PricingConfig())


class TestRenewalSweep:
    """Tests for writing successors to expired arrangements."""

    async def test_an_expired_arrangement_is_renewed(
        self, service: QuoteService
    ) -> None:
        """The ordinary case."""
        service.quotes.list_renewable.return_value = [_parent()]

        renewed = await service.renew_due(TODAY)

        assert len(renewed) == 1
        assert renewed[0].renewed_from_id == "quote-1"

    async def test_the_successor_covers_the_period_that_follows(
        self, service: QuoteService
    ) -> None:
        """**A renewal continues the arrangement; it does not repeat it.**

        Notes:
            The services are shifted by the parent's own span, so a four-week
            arrangement renews into the four weeks after it rather than
            overlapping itself — which would put two visits on the same morning
            and make the planner choose one.
        """
        service.quotes.list_renewable.return_value = [_parent()]

        successor = (await service.renew_due(TODAY))[0]

        assert min(line.service_date for line in successor.lines) > LAST_SERVICE

    async def test_the_successor_keeps_the_shape_of_the_arrangement(
        self, service: QuoteService
    ) -> None:
        """Same services, same weekdays, same customer.

        Notes:
            The gap between the two visits is preserved, which is what keeps a
            Monday-and-Friday arrangement on Mondays and Fridays.
        """
        service.quotes.list_renewable.return_value = [_parent()]

        successor = (await service.renew_due(TODAY))[0]
        days = sorted(line.service_date for line in successor.lines)

        assert successor.customer_id == "customer-1"
        assert len(days) == 2
        assert (days[1] - days[0]) == (LAST_SERVICE - FIRST_SERVICE)

    async def test_the_successor_is_priced_at_todays_catalog(
        self, service: QuoteService
    ) -> None:
        """**A rate change reaches the next period, not the one already agreed.**

        Notes:
            The parent's stored amounts are what the customer accepted and must
            never move. The successor is a new offer, so it is priced against
            the catalog as it stands when the renewal runs — here, a rate that
            has since doubled.
        """
        service.types.get_many.return_value = {"type-1": _type("63.810")}
        parent = _parent()
        service.quotes.list_renewable.return_value = [parent]

        successor = (await service.renew_due(TODAY))[0]

        assert successor.total_ttc() > parent.total_ttc()

    async def test_the_successor_carries_a_fresh_validity_window(
        self, service: QuoteService
    ) -> None:
        """It is issued on the day it is written, not the day its parent was."""
        service.quotes.list_renewable.return_value = [_parent()]

        successor = (await service.renew_due(TODAY))[0]

        assert successor.issued_on == TODAY
        assert successor.valid_until is not None
        assert successor.valid_until > TODAY

    async def test_the_successor_renews_in_its_turn(
        self, service: QuoteService
    ) -> None:
        """An arrangement that renews once keeps renewing until stopped.

        Notes:
            That is what a standing arrangement means. Turning renewal off on
            the successor, or interrupting it, is how it ends — both of which
            are one call away.
        """
        service.quotes.list_renewable.return_value = [_parent()]

        successor = (await service.renew_due(TODAY))[0]

        assert successor.auto_renew is True

    async def test_the_lines_are_repriced_rather_than_copied(
        self, service: QuoteService
    ) -> None:
        """The parent's identifiers must not follow its services across.

        Notes:
            A copied line identifier would make the successor's line collide
            with the parent's on write, and — worse — make a planned
            intervention ambiguous about which period's visit it fulfils.
        """
        service.quotes.list_renewable.return_value = [_parent()]

        successor = (await service.renew_due(TODAY))[0]

        assert all(line.id is None for line in successor.lines) or all(
            line.id != parent_line.id
            for line, parent_line in zip(successor.lines, _parent().lines)
        )


class TestRenewalIsSafeToRepeat:
    """Tests for the property that lets this run on a timer."""

    async def test_a_quote_already_renewed_is_skipped(
        self, service: QuoteService
    ) -> None:
        """**The check the whole design rests on.**

        Notes:
            Two workers waking together, a retry after a partial failure, or a
            manager pressing the button because the timer looked stuck — each
            would otherwise write a successor, and the customer would be billed
            twice for one period. ``renewed_from_id`` records the parent, and
            a parent that already has a successor is left alone.
        """
        service.quotes.list_renewable.return_value = [_parent()]
        service.quotes.has_successor.return_value = True

        renewed = await service.renew_due(TODAY)

        assert renewed == []
        service.quotes.create.assert_not_awaited()

    async def test_an_interrupted_arrangement_is_not_renewed(
        self, service: QuoteService
    ) -> None:
        """An end date is the customer saying stop.

        Notes:
            Checked in the service as well as in the repository query. The
            query filters on it, but a quote interrupted between the query and
            the write would otherwise be renewed anyway — and renewing an
            arrangement somebody has just cancelled is the worst of the
            failures available here.
        """
        service.quotes.list_renewable.return_value = [
            _parent(interrupted_on=LAST_SERVICE)
        ]

        renewed = await service.renew_due(TODAY)

        assert renewed == []
        service.quotes.create.assert_not_awaited()

    async def test_nothing_due_writes_nothing(self, service: QuoteService) -> None:
        """Most days, which is why this is safe to run often."""
        service.quotes.list_renewable.return_value = []

        assert await service.renew_due(TODAY) == []
        service.quotes.create.assert_not_awaited()

    async def test_each_parent_is_asked_about_separately(
        self, service: QuoteService
    ) -> None:
        """One already-renewed arrangement does not stop the others.

        Notes:
            A sweep that gave up on the first skip would leave every later
            arrangement unrenewed, and nobody would notice until a family rang
            to ask where their carer was.
        """
        renewed_already, still_due = _parent(), _parent(id="quote-2", reference="DEV-2")
        service.quotes.list_renewable.return_value = [renewed_already, still_due]
        service.quotes.has_successor.side_effect = [True, False]

        renewed = await service.renew_due(TODAY)

        assert len(renewed) == 1
        assert renewed[0].renewed_from_id == "quote-2"


class TestAutoRenewFlag:
    """Tests for opting an arrangement in and out."""

    @pytest.mark.parametrize("enabled", [True, False])
    async def test_the_flag_is_stored(
        self, service: QuoteService, enabled: bool
    ) -> None:
        """Both directions.

        Args:
            enabled (bool): The value under test.
        """
        service.quotes.get.return_value = _parent(auto_renew=not enabled)
        service.quotes.update.side_effect = lambda quote: quote

        result = await service.set_auto_renew("quote-1", enabled)

        assert result.auto_renew is enabled

    async def test_turning_it_on_renews_nothing_yet(
        self, service: QuoteService
    ) -> None:
        """A flag, not an act.

        Notes:
            Nothing happens until the quote reaches its validity date, so
            turning renewal on and off again before then costs nothing — which
            is what makes it safe to offer as a switch on a screen.
        """
        service.quotes.get.return_value = _parent(auto_renew=False)
        service.quotes.update.side_effect = lambda quote: quote

        await service.set_auto_renew("quote-1", True)

        service.quotes.create.assert_not_awaited()
