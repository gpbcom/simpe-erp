from __future__ import annotations

# Standard library imports
from datetime import date, time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.catalog.intervention_type import InterventionType
from models.configuration.pricing_config import PricingConfig
from models.enums import RegistrationStatus, ServiceCategory, UserRole
from models.geo.postal_address import PostalAddress
from models.people.customer import Customer
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from models.schemas.requests.quoting.quote_create_request import QuoteCreateRequest
from service.quotes.exceptions import (
    MTQuoteNotFound,
    MTQuoteTeamForbidden,
    MTQuoteUnassignable,
)
from service.quotes.quotes import QuoteService

SERVICE_DAY = date(2026, 9, 1)


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


def _customer() -> Customer:
    """Build the household every quote here is addressed to.

    Returns:
        Customer: The household, already located.
    """
    return Customer(
        id="customer-1",
        first_name="Marie",
        last_name="Durand",
        phone_number="+33612345678",
        email="marie.durand@example.fr",
        address=PostalAddress(
            street="1 rue de Rivoli",
            postal_code="75001",
            city="Paris",
            country="France",
            latitude=48.8566,
            longitude=2.3522,
        ),
        registration_status=RegistrationStatus.ACTIVE,
    )


def _payload() -> QuoteCreateRequest:
    """Build a one-line request to open a quote.

    Returns:
        QuoteCreateRequest: The payload, carrying no team and no company.
    """
    return QuoteCreateRequest(
        reference="Q-2026-001",
        customer_id="customer-1",
        lines=[
            QuoteLine(
                name="Toilette matin",
                intervention_type_id="type-1",
                service_category=ServiceCategory.NECESSITY,
                service_date=SERVICE_DAY,
                earliest_start=time(9, 0),
                latest_end=time(11, 0),
                duration_minutes=120,
            )
        ],
    )


def _quote(team_id: str = "team-1") -> Quote:
    """Build a stored quote already attributed to a team.

    Args:
        team_id (str): The team it currently belongs to.

    Returns:
        Quote: The quote.
    """
    return Quote(
        id="quote-1",
        company_id="company-1",
        team_id=team_id,
        reference="Q-2026-001",
        customer_id="customer-1",
    )


def _caller(role: UserRole = UserRole.MANAGER) -> User:
    """Build the account acting on the quote.

    Args:
        role (UserRole): The role it holds.

    Returns:
        User: The account.
    """
    return User(
        id="user-1",
        email="marc@simple-erp.fr",
        full_name="Marc Dubois",
        hashed_password="x" * 20,
        role=role,
        company_id="company-1",
    )


@pytest.fixture
def teams() -> AsyncMock:
    """Return a stubbed team service.

    Returns:
        AsyncMock: The service double, attributing everything to ``team-1``.
    """
    stub = AsyncMock()
    stub.attribute.return_value = "team-1"
    stub.readable_team_ids.return_value = None
    return stub


@pytest.fixture
def customers() -> AsyncMock:
    """Return a stubbed customer store.

    Returns:
        AsyncMock: The store double, holding one located household.
    """
    stub = AsyncMock()
    stub.get.return_value = _customer()
    return stub


@pytest.fixture
def quotes() -> AsyncMock:
    """Return a stubbed quote store.

    Returns:
        AsyncMock: The store double, echoing back what it is given.
    """
    stub = AsyncMock()
    stub.create.side_effect = lambda quote: quote
    stub.get.return_value = _quote()
    stub.update.side_effect = lambda quote: quote
    return stub


@pytest.fixture
def service(quotes: AsyncMock, teams: AsyncMock, customers: AsyncMock) -> QuoteService:
    """Return the service under test.

    Args:
        quotes (AsyncMock): The quote store.
        teams (AsyncMock): The team service.
        customers (AsyncMock): The customer store.

    Returns:
        QuoteService: The service.
    """
    types = AsyncMock()
    types.get_many.return_value = {"type-1": _type()}
    return QuoteService(
        quotes=quotes,
        types=types,
        config=PricingConfig(),
        teams=teams,
        customers=customers,
        logger=MagicMock(),
    )


class TestAttributingANewQuote:
    """Tests for deciding which team delivers a newly written quote."""

    async def test_the_quote_is_filed_with_the_chosen_team(
        self, service: QuoteService, teams: AsyncMock
    ) -> None:
        """The rule's answer is what lands on the stored record."""
        teams.attribute.return_value = "team-7"
        stored = await service.create(_payload(), "company-1", author_id="user-1")
        assert stored.team_id == "team-7"

    async def test_the_household_decides_the_team(
        self, service: QuoteService, teams: AsyncMock
    ) -> None:
        """The customer is resolved and handed to the rule, not the identifier.

        Notes:
            The rule measures a distance from where the household lives, so
            passing the identifier would make it read the customer a second
            time — or, worse, be unable to.
        """
        await service.create(_payload(), "company-1")
        company_id, customer = teams.attribute.await_args.args
        assert company_id == "company-1"
        assert customer.id == "customer-1"

    async def test_the_company_comes_from_the_caller(
        self, service: QuoteService
    ) -> None:
        """No payload can file work into another agency."""
        stored = await service.create(_payload(), "company-9")
        assert stored.company_id == "company-9"

    async def test_the_author_comes_from_the_caller(
        self, service: QuoteService
    ) -> None:
        """A quote naming somebody else as its author would land in their list."""
        stored = await service.create(_payload(), "company-1", author_id="user-3")
        assert stored.authored_by == "user-3"

    async def test_an_unknown_household_is_refused(
        self, service: QuoteService, customers: AsyncMock
    ) -> None:
        """A quote for nobody could never become a visit."""
        customers.get.return_value = None
        with pytest.raises(MTQuoteUnassignable):
            await service.create(_payload(), "company-1")

    async def test_a_company_with_no_team_is_refused(
        self, service: QuoteService, teams: AsyncMock
    ) -> None:
        """Stored unattributed, the work would go quiet rather than wrong.

        Notes:
            This is the case the whole refusal exists for: the quote would be
            priced, sent and accepted, and then read by no planning run, because
            every run asks for one team's work.
        """
        teams.attribute.return_value = None
        with pytest.raises(MTQuoteUnassignable):
            await service.create(_payload(), "company-1")

    async def test_nothing_is_stored_when_no_team_can_be_found(
        self, service: QuoteService, teams: AsyncMock, quotes: AsyncMock
    ) -> None:
        """The refusal happens before the write, not after it."""
        teams.attribute.return_value = None
        with pytest.raises(MTQuoteUnassignable):
            await service.create(_payload(), "company-1")
        quotes.create.assert_not_awaited()

    async def test_the_team_is_resolved_before_the_lines_are_priced(
        self, service: QuoteService, teams: AsyncMock
    ) -> None:
        """A company with no team hears that, not about a missing type.

        Notes:
            Both orders reach the same verdict. This one means the message names
            the problem the caller can actually act on.
        """
        teams.attribute.return_value = None
        payload = _payload()
        payload.lines[0].intervention_type_id = "type-that-does-not-exist"
        with pytest.raises(MTQuoteUnassignable):
            await service.create(payload, "company-1")


class TestMovingAQuoteBetweenTeams:
    """Tests for correcting an attribution after the fact."""

    async def test_the_quote_takes_the_new_team(self, service: QuoteService) -> None:
        """The move is the whole operation."""
        moved = await service.reassign_team("quote-1", "team-2", _caller())
        assert moved.team_id == "team-2"

    async def test_an_administrator_may_move_it_anywhere(
        self, service: QuoteService, teams: AsyncMock
    ) -> None:
        """``None`` from the narrowing means every team, not no team."""
        teams.readable_team_ids.return_value = None
        moved = await service.reassign_team(
            "quote-1", "team-2", _caller(UserRole.ADMIN)
        )
        assert moved.team_id == "team-2"

    async def test_a_manager_may_not_move_it_out_of_a_team_they_do_not_run(
        self, service: QuoteService, teams: AsyncMock
    ) -> None:
        """Taking work off a colleague's plan is not theirs to do."""
        teams.readable_team_ids.return_value = ["team-2"]
        with pytest.raises(MTQuoteTeamForbidden):
            await service.reassign_team("quote-1", "team-2", _caller())

    async def test_a_manager_may_not_move_it_into_a_team_they_do_not_run(
        self, service: QuoteService, teams: AsyncMock
    ) -> None:
        """It would commit assistants they do not manage to work.

        Notes:
            The mirror of the test above, and both are needed: checking only the
            destination lets a manager empty somebody else's queue, and checking
            only the origin lets them fill one.
        """
        teams.readable_team_ids.return_value = ["team-1"]
        with pytest.raises(MTQuoteTeamForbidden):
            await service.reassign_team("quote-1", "team-2", _caller())

    async def test_a_quote_of_another_company_is_not_found(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """Answered 404, so an identifier cannot be confirmed to exist."""
        quotes.get.return_value = _quote().model_copy(
            update={"company_id": "company-9"}
        )
        with pytest.raises(MTQuoteNotFound):
            await service.reassign_team("quote-1", "team-2", _caller())

    async def test_the_destination_team_must_exist(
        self, service: QuoteService, teams: AsyncMock
    ) -> None:
        """Moving work onto a team that is gone would lose it silently."""
        teams.get_for.side_effect = MTQuoteNotFound("no such team")
        with pytest.raises(MTQuoteNotFound):
            await service.reassign_team("quote-1", "team-2", _caller())
