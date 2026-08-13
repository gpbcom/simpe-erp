from __future__ import annotations

# Standard library imports
from datetime import date, time
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.configuration.holiday_surcharge import HolidaySurcharge
from models.configuration.pricing_config import PricingConfig
from models.enums import (
    QuoteStatus,
    ServiceCategory,
    UnplacedReason,
    Weekday,
)
from models.planning.planning_run.unplaced_quote import UnplacedQuote
from models.planning.planning_run.unplaced_requirement import UnplacedRequirement
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from models.quoting.exceptions import MTQuoteLineWindowTooShort
from service.quotes.exceptions import MTQuoteLineNotFound, MTQuoteNotFound
from service.quotes.quotes import QuoteService
from storage.repositories.catalog.intervention_type import InterventionTypeRepository
from storage.repositories.quoting.quote import QuoteRepository

#: A Tuesday, which carries no surcharge, and the Sunday after it, which does.
TUESDAY = date(2026, 8, 18)
SUNDAY = date(2026, 8, 23)
LINE_ID = "line-1"
QUOTE_ID = "quote-1"


def _config() -> PricingConfig:
    """Return the agency's pricing rules.

    Returns:
        PricingConfig: A weekday base rate with a Sunday surcharge, so a move
        across the week is visible in the total.
    """
    return PricingConfig(
        base_hourly_rate_ht=Decimal("31.905"),
        weekday_surcharges={Weekday.SUNDAY: Decimal("0.25")},
        holiday_surcharges=[
            HolidaySurcharge(
                month=12, day=25, surcharge=Decimal("0.50"), label="Christmas Day"
            )
        ],
    )


def _line(day: date = TUESDAY, minutes: int = 120) -> QuoteLine:
    """Build a two-hour morning line.

    Args:
        day (date): The day it is delivered on.
        minutes (int): How long it takes.

    Returns:
        QuoteLine: The unpriced line.
    """
    return QuoteLine(
        id=LINE_ID,
        name="Entretien du logement",
        intervention_type_id="type-necessity",
        service_category=ServiceCategory.NECESSITY,
        service_date=day,
        earliest_start=time(9, 0),
        latest_end=time(13, 0),
        duration_minutes=minutes,
    )


def _feedback() -> UnplacedQuote:
    """Build the note a planner leaves when it returns a quote.

    Returns:
        UnplacedQuote: One unplaced visit, naming the line it was sold on.
    """
    return UnplacedQuote(
        quote_reference="D-2648",
        customer_id="cust-1",
        customer_name="Jeanne Vincent",
        visits=[
            UnplacedRequirement(
                requirement_id="req-1",
                quote_line_id=LINE_ID,
                name="Entretien du logement",
                customer_id="cust-1",
                day=TUESDAY,
                reason=UnplacedReason.NO_FEASIBLE_SLOT,
            )
        ],
    )


def _quote(lines: Optional[List[QuoteLine]] = None) -> Quote:
    """Build a quote that a planner has returned for validation.

    Args:
        lines (Optional[List[QuoteLine]]): The lines it carries.

    Returns:
        Quote: The quote under test.
    """
    return Quote(
        id=QUOTE_ID,
        company_id="company-1",
        team_id="team-1",
        reference="D-2648",
        customer_id="cust-1",
        status=QuoteStatus.PENDING_VALIDATION,
        lines=lines if lines is not None else [_line()],
        planning_feedback=_feedback(),
    )


@pytest.fixture
def quotes() -> MagicMock:
    """Return a quote store double holding one returned quote.

    Returns:
        MagicMock: The double, whose ``update`` echoes what it is given.
    """
    repository = MagicMock(spec=QuoteRepository)
    repository.get = AsyncMock(return_value=_quote())
    repository.update = AsyncMock(side_effect=lambda quote: quote)
    return repository


@pytest.fixture
def types() -> MagicMock:
    """Return a catalogue double offering the one type the line sells.

    Returns:
        MagicMock: The double.
    """
    catalogue: Dict[str, InterventionType] = {
        "type-necessity": InterventionType(
            id="type-necessity",
            name="Entretien du logement",
            code="ENTRETIEN",
            service_category=ServiceCategory.NECESSITY,
        )
    }
    repository = MagicMock(spec=InterventionTypeRepository)
    # ``_price`` fetches every type in one query rather than one per line, so
    # this is the method the pricing path actually reaches.
    repository.get_many = AsyncMock(
        side_effect=lambda type_ids: {
            type_id: catalogue[type_id] for type_id in type_ids if type_id in catalogue
        }
    )
    return repository


@pytest.fixture
def service(quotes: MagicMock, types: MagicMock) -> QuoteService:
    """Return the service under test.

    Args:
        quotes (MagicMock): The quote store double.
        types (MagicMock): The catalogue double.

    Returns:
        QuoteService: The service.
    """
    return QuoteService(
        quotes=quotes,
        types=types,
        config=_config(),
        teams=AsyncMock(),
        customers=AsyncMock(),
    )


class TestAcceptingAnOfferedSlot:
    """Tests for moving one line onto a time the planner offered."""

    async def test_the_line_takes_the_new_day_and_window(
        self, service: QuoteService
    ) -> None:
        """**What the operator clicked is what the quote now says.**

        Args:
            service (QuoteService): The service under test.
        """
        updated = await service.reschedule_line(
            QUOTE_ID, LINE_ID, date(2026, 8, 17), 870, 990
        )

        moved = updated.lines[0]
        assert moved.service_date == date(2026, 8, 17)
        assert moved.earliest_start == time(14, 30)
        assert moved.latest_end == time(16, 30)

    async def test_the_status_does_not_move(self, service: QuoteService) -> None:
        """**Accepting a time answers when, never whether.**

        Args:
            service (QuoteService): The service under test.

        Notes:
            The quote came back because its work would not fit. Choosing a new
            time is a scheduling decision; approving the work is a separate one
            that a manager still has to make. Moving the status here would let
            the first silently perform the second.
        """
        updated = await service.reschedule_line(
            QUOTE_ID, LINE_ID, date(2026, 8, 17), 870, 990
        )

        assert updated.status is QuoteStatus.PENDING_VALIDATION

    async def test_the_planning_note_is_cleared(self, service: QuoteService) -> None:
        """Its reasons describe a date that has just changed.

        Args:
            service (QuoteService): The service under test.

        Notes:
            Leaving it would keep offering slots computed against a plan that
            no longer applies, and invite a second click that silently
            overwrites the first.
        """
        updated = await service.reschedule_line(
            QUOTE_ID, LINE_ID, date(2026, 8, 17), 870, 990
        )

        assert updated.planning_feedback is None

    async def test_moving_onto_a_sunday_reprices(self, service: QuoteService) -> None:
        """**The surcharge is a property of the day, so the total follows it.**

        Args:
            service (QuoteService): The service under test.

        Notes:
            A quote whose figures did not follow from its own dates would print
            a document an accountant cannot reconcile. Two hours at 31.905 is
            63.81 on a weekday and 79.76 with the Sunday quarter added.
        """
        weekday = await service.reschedule_line(QUOTE_ID, LINE_ID, TUESDAY, 540, 780)
        assert weekday.lines[0].total_ht == Decimal("63.81")

        sunday = await service.reschedule_line(QUOTE_ID, LINE_ID, SUNDAY, 540, 780)
        assert sunday.lines[0].total_ht == Decimal("79.76")

    async def test_the_other_lines_are_untouched(
        self, service: QuoteService, quotes: MagicMock
    ) -> None:
        """Only the line that was clicked moves.

        Args:
            service (QuoteService): The service under test.
            quotes (MagicMock): The quote store double.
        """
        other = _line().model_copy(update={"id": "line-2", "service_date": SUNDAY})
        quotes.get = AsyncMock(return_value=_quote([_line(), other]))

        updated = await service.reschedule_line(
            QUOTE_ID, LINE_ID, date(2026, 8, 17), 870, 990
        )

        untouched = next(line for line in updated.lines if line.id == "line-2")
        assert untouched.service_date == SUNDAY
        assert untouched.earliest_start == time(9, 0)

    async def test_no_assistant_is_recorded(self, service: QuoteService) -> None:
        """**A quote says what is sold and when, never who does it.**

        Args:
            service (QuoteService): The service under test.

        Notes:
            The offered slot names somebody, and that is what makes it worth
            reading — but the planner assigns the work on its next run, and a
            preference stored here would be a promise nothing keeps.
        """
        updated = await service.reschedule_line(
            QUOTE_ID, LINE_ID, date(2026, 8, 17), 870, 990
        )

        assert not hasattr(updated.lines[0], "hca_id")
        assert "hca" not in updated.lines[0].model_dump()


class TestWhatRescheduleRefuses:
    """Tests for the offers that can no longer be honoured."""

    async def test_a_line_the_quote_no_longer_carries(
        self, service: QuoteService
    ) -> None:
        """**A stale offer, which happens routinely.**

        Args:
            service (QuoteService): The service under test.

        Notes:
            The slots on screen were computed when the planner last ran. A line
            edited away since leaves the offer pointing at nothing, and the
            caller needs to know it is the line that is gone rather than the
            quote.
        """
        with pytest.raises(MTQuoteLineNotFound):
            await service.reschedule_line(
                QUOTE_ID, "line-gone", date(2026, 8, 17), 870, 990
            )

    async def test_a_window_narrower_than_the_work(self, service: QuoteService) -> None:
        """Refused here rather than failing every run afterwards.

        Args:
            service (QuoteService): The service under test.

        Notes:
            The line takes two hours. A ninety-minute window cannot hold it,
            and storing one would produce a quote that no planning run can
            ever place.
        """
        with pytest.raises(MTQuoteLineWindowTooShort):
            await service.reschedule_line(
                QUOTE_ID, LINE_ID, date(2026, 8, 17), 870, 960
            )

    async def test_a_quote_that_vanished_mid_write(
        self, service: QuoteService, quotes: MagicMock
    ) -> None:
        """A write that lands on nothing is an error, not a silent success.

        Args:
            service (QuoteService): The service under test.
            quotes (MagicMock): The quote store double.
        """
        quotes.update = AsyncMock(return_value=None)

        with pytest.raises(MTQuoteNotFound):
            await service.reschedule_line(
                QUOTE_ID, LINE_ID, date(2026, 8, 17), 870, 990
            )
