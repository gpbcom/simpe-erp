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
from models.enums import InterventionStatus, ServiceCategory
from models.planning.intervention import Intervention
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from service.intervention_types.exceptions import MTInterventionTypeNotFound
from service.planning.exceptions import (
    MTInterventionNotFound,
    MTInterventionNotQuoted,
)
from service.planning.interventions import InterventionService
from service.quotes.exceptions import MTQuoteNotFound

MONDAY = date(2026, 8, 3)
NECESSITY = "type-necessity"
COMFORT = "type-comfort"


def _type(
    type_id: str = NECESSITY,
    category: ServiceCategory = ServiceCategory.NECESSITY,
    name: str = "Aide a la toilette",
) -> InterventionType:
    """Build a catalogue entry.

    Args:
        type_id (str): The identifier to assign.
        category (ServiceCategory): The VAT category it usually falls under.
        name (str): Its display name.

    Returns:
        InterventionType: The entry.
    """
    return InterventionType(
        id=type_id,
        name=name,
        code=type_id.upper().replace("-", "_"),
        service_category=category,
        base_hourly_rate_ht=Decimal("30.00"),
    )


def _line(line_id: str, name: str = "Aide a la toilette") -> QuoteLine:
    """Build a two-hour quote line.

    Args:
        line_id (str): The identifier to assign.
        name (str): What the service is called on the quote.

    Returns:
        QuoteLine: The line.
    """
    return QuoteLine(
        id=line_id,
        name=name,
        intervention_type_id=NECESSITY,
        service_category=ServiceCategory.NECESSITY,
        service_date=MONDAY,
        earliest_start=time(9, 0),
        latest_end=time(13, 0),
        duration_minutes=120,
    )


def _quote(lines: List[QuoteLine]) -> Quote:
    """Build a quote carrying lines.

    Args:
        lines (List[QuoteLine]): The lines it sells.

    Returns:
        Quote: The quote.
    """
    return Quote(
        id="quote-1",
        reference="D-2601",
        customer_id="customer-1",
        lines=lines,
    )


def _intervention(
    line_id: str = "line-1", name: str = "Aide a la toilette"
) -> Intervention:
    """Build a scheduled visit.

    Args:
        line_id (str): The quote line it was scheduled from.
        name (str): What the calendar block is labelled.

    Returns:
        Intervention: The visit.
    """
    return Intervention(
        id="visit-1",
        planning_run_id="run-1",
        name=name,
        intervention_type_id=NECESSITY,
        quote_line_id=line_id,
        hca_id="hca-1",
        hca_full_name="Luc Martin",
        customer_id="customer-1",
        day=MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        address={
            "street": "12 rue de Rivoli",
            "postal_code": "75004",
            "city": "Paris",
            "latitude": 48.8566,
            "longitude": 2.3522,
        },
        status=InterventionStatus.PLANNED,
    )


@pytest.fixture
def interventions() -> AsyncMock:
    """Return a stand-in visit repository.

    Returns:
        AsyncMock: The repository.
    """
    repository = AsyncMock()
    repository.get.return_value = _intervention()
    repository.delete.return_value = True
    repository.update.side_effect = lambda visit: visit
    return repository


@pytest.fixture
def quotes() -> AsyncMock:
    """Return a stand-in quote service.

    Returns:
        AsyncMock: The service, answering with a two-line quote.
    """
    service = AsyncMock()
    service.get_by_line.return_value = _quote([_line("line-1"), _line("line-2")])
    service.replace_lines.side_effect = lambda quote_id, quote: quote
    return service


@pytest.fixture
def types() -> AsyncMock:
    """Return a stand-in catalogue.

    Returns:
        AsyncMock: The catalogue, holding a necessity and a comfort entry.
    """
    catalogue = AsyncMock()
    catalogue.get.side_effect = lambda type_id: {
        NECESSITY: _type(),
        COMFORT: _type(COMFORT, ServiceCategory.COMFORT, "Compagnie"),
    }.get(type_id)
    return catalogue


@pytest.fixture
def service(
    interventions: AsyncMock, quotes: AsyncMock, types: AsyncMock
) -> InterventionService:
    """Return the service under test.

    Args:
        interventions (AsyncMock): The visit repository.
        quotes (AsyncMock): The quote service.
        types (AsyncMock): The catalogue.

    Returns:
        InterventionService: The service.
    """
    return InterventionService(interventions=interventions, quotes=quotes, types=types)


class TestCancellingAVisit:
    """Tests that cancelling a visit also stops it being billed for."""

    @pytest.mark.asyncio
    async def test_the_visit_is_removed(
        self, service: InterventionService, interventions: AsyncMock
    ) -> None:
        """The calendar entry goes."""
        await service.delete("visit-1")
        interventions.delete.assert_awaited_once_with("visit-1")

    @pytest.mark.asyncio
    async def test_its_quote_line_goes_with_it(
        self, service: InterventionService, quotes: AsyncMock
    ) -> None:
        """The line goes too, or the next run puts the visit straight back.

        Notes:
            This is the whole point of the operation rather than a nicety. The
            planner rebuilds a period from the quote lines, so a visit deleted
            on its own reappears within the hour and nobody connects the two.
        """
        await service.delete("visit-1")
        _, sent = quotes.replace_lines.await_args.args
        assert [line.id for line in sent.lines] == ["line-2"]

    @pytest.mark.asyncio
    async def test_the_quote_is_repriced(
        self, service: InterventionService, quotes: AsyncMock
    ) -> None:
        """Removing an hour of care changes what the customer owes."""
        await service.delete("visit-1")
        quotes.replace_lines.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_quote_left_with_nothing_is_deleted(
        self, service: InterventionService, quotes: AsyncMock
    ) -> None:
        """An empty quote can be neither priced, validated nor printed."""
        quotes.get_by_line.return_value = _quote([_line("line-1")])
        assert await service.delete("visit-1") is None
        quotes.delete.assert_awaited_once_with("quote-1")
        quotes.replace_lines.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_unknown_visit_is_refused(
        self, service: InterventionService, interventions: AsyncMock
    ) -> None:
        """A 404, not a silent success."""
        interventions.get.return_value = None
        with pytest.raises(MTInterventionNotFound):
            await service.delete("visit-404")

    @pytest.mark.asyncio
    async def test_a_visit_whose_line_has_vanished_is_refused(
        self, service: InterventionService, quotes: AsyncMock
    ) -> None:
        """The calendar is never edited on its own."""
        quotes.get_by_line.side_effect = MTQuoteNotFound("gone")
        with pytest.raises(MTInterventionNotQuoted):
            await service.delete("visit-1")


class TestSellingAVisitAsSomethingElse:
    """Tests re-classifying a visit and repricing the quote behind it."""

    @pytest.mark.asyncio
    async def test_the_line_takes_the_new_type(
        self, service: InterventionService, quotes: AsyncMock
    ) -> None:
        """The quote is what actually changes."""
        await service.change_type("visit-1", COMFORT)
        _, sent = quotes.replace_lines.await_args.args
        changed = next(line for line in sent.lines if line.id == "line-1")
        assert changed.intervention_type_id == COMFORT

    @pytest.mark.asyncio
    async def test_the_vat_category_follows_the_catalogue(
        self, service: InterventionService, quotes: AsyncMock
    ) -> None:
        """Which is what makes the repricing change the tax, not only the rate."""
        await service.change_type("visit-1", COMFORT)
        _, sent = quotes.replace_lines.await_args.args
        changed = next(line for line in sent.lines if line.id == "line-1")
        assert changed.service_category is ServiceCategory.COMFORT

    @pytest.mark.asyncio
    async def test_the_other_lines_are_left_alone(
        self, service: InterventionService, quotes: AsyncMock
    ) -> None:
        """One visit was re-classified, not the whole quote."""
        await service.change_type("visit-1", COMFORT)
        _, sent = quotes.replace_lines.await_args.args
        untouched = next(line for line in sent.lines if line.id == "line-2")
        assert untouched.intervention_type_id == NECESSITY

    @pytest.mark.asyncio
    async def test_a_catalogue_label_is_renamed(
        self, service: InterventionService, quotes: AsyncMock
    ) -> None:
        """A line still carrying the catalogue wording gets the new wording."""
        await service.change_type("visit-1", COMFORT)
        _, sent = quotes.replace_lines.await_args.args
        changed = next(line for line in sent.lines if line.id == "line-1")
        assert changed.name == "Compagnie"

    @pytest.mark.asyncio
    async def test_a_hand_written_label_is_kept(
        self, service: InterventionService, quotes: AsyncMock
    ) -> None:
        """Somebody typed that wording for a reason."""
        quotes.get_by_line.return_value = _quote(
            [_line("line-1", name="Toilette - etage"), _line("line-2")]
        )
        await service.change_type("visit-1", COMFORT)
        _, sent = quotes.replace_lines.await_args.args
        changed = next(line for line in sent.lines if line.id == "line-1")
        assert changed.name == "Toilette - etage"

    @pytest.mark.asyncio
    async def test_the_calendar_is_corrected_too(
        self, service: InterventionService, interventions: AsyncMock
    ) -> None:
        """Or the manager reads back the service they just changed away from."""
        await service.change_type("visit-1", COMFORT)
        stored = interventions.update.await_args.args[0]
        assert stored.intervention_type_id == COMFORT
        assert stored.name == "Compagnie"

    @pytest.mark.asyncio
    async def test_an_unknown_type_is_refused(
        self, service: InterventionService, quotes: AsyncMock
    ) -> None:
        """Before anything is written, not after."""
        with pytest.raises(MTInterventionTypeNotFound):
            await service.change_type("visit-1", "type-404")
        quotes.replace_lines.assert_not_awaited()


class TestAVisitWhoseLineIsGone:
    """Tests the one inconsistency neither operation will paper over."""

    @pytest.mark.asyncio
    async def test_re_classifying_is_refused(
        self, service: InterventionService, quotes: AsyncMock
    ) -> None:
        """A calendar that disagrees with the paperwork is the worse outcome."""
        quotes.get_by_line.side_effect = MTQuoteNotFound("gone")
        with pytest.raises(MTInterventionNotQuoted):
            await service.change_type("visit-1", COMFORT)

    @pytest.mark.asyncio
    async def test_a_line_missing_from_its_own_quote_is_refused(
        self, service: InterventionService, quotes: AsyncMock
    ) -> None:
        """The lookup found a quote that does not carry the line."""
        quotes.get_by_line.return_value = _quote([_line("line-9")])
        with pytest.raises(MTInterventionNotQuoted):
            await service.delete("visit-1")


class TestTheServiceIsConstructed:
    """Tests the wiring the API depends on."""

    def test_it_holds_its_collaborators(
        self,
        interventions: AsyncMock,
        quotes: AsyncMock,
        types: AsyncMock,
        service: InterventionService,
    ) -> None:
        """Named attributes, so the dependency graph is readable."""
        assert service.interventions is interventions
        assert service.quotes is quotes
        assert service.types is types

    def test_it_defaults_its_logger(
        self, interventions: AsyncMock, quotes: AsyncMock, types: AsyncMock
    ) -> None:
        """A service without a logger still logs, under its own module name."""
        built = InterventionService(
            interventions=interventions, quotes=quotes, types=types
        )
        assert built.logger.name == "service.planning.interventions"


class TestOptionalCollaborators:
    """Tests the corner the repository stubs leave open."""

    @pytest.mark.asyncio
    async def test_a_visit_with_no_identifier_is_still_deletable(
        self, service: InterventionService, interventions: AsyncMock
    ) -> None:
        """The caller passes the identifier; the model's own may be unset.

        Notes:
            Interventions read back from the store always carry one, but the
            model allows ``None`` and the delete path must not depend on it.
        """
        without_id: Optional[Intervention] = _intervention().model_copy(
            update={"id": None}
        )
        interventions.get.return_value = without_id
        await service.delete("visit-1")
        interventions.delete.assert_awaited_once_with("visit-1")
