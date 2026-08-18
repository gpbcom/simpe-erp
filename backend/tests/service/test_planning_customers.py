from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import Optional
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.configuration.planning_config import PlanningConfig
from models.enums import InterventionStatus, UserRole
from models.people.customer import Customer
from models.planning.intervention import Intervention
from service.planning.exceptions import (
    MTPlanningCustomerNotFound,
    MTPlanningForbidden,
)
from service.planning.plannings import PlanningService

MONDAY = date(2026, 8, 3)
SUNDAY = date(2026, 8, 9)
ADDRESS = {
    "street": "12 rue de Rivoli",
    "postal_code": "75004",
    "city": "Paris",
    "latitude": 48.8566,
    "longitude": 2.3522,
}


def _user(
    role: UserRole,
    hca_id: Optional[str] = None,
    customer_id: Optional[str] = None,
) -> User:
    """Build an authenticated account.

    Args:
        role (UserRole): What the account may do.
        hca_id (Optional[str]): The assistant record it is bound to, if any.
        customer_id (Optional[str]): The household it belongs to, if any.

    Returns:
        User: The account.
    """
    return User(
        company_id="company-1",
        id=f"user-{role.value}",
        email=f"{role.value}@example.com",
        full_name=f"Test {role.value.title()}",
        hashed_password="$2b$12$" + "a" * 53,
        role=role,
        hca_id=hca_id,
        customer_id=customer_id,
    )


def _household(customer_id: str = "customer-1", last_name: str = "Durand") -> Customer:
    """Build a household.

    Args:
        customer_id (str): The identifier to assign.
        last_name (str): Their family name.

    Returns:
        Customer: The household.
    """
    return Customer(
        id=customer_id,
        first_name="Marie",
        last_name=last_name,
        phone_number="+33612345678",
        email=f"{customer_id}@example.fr",
        address=ADDRESS,
    )


def _visit(
    customer_id: str = "customer-1",
    visit_id: str = "visit-1",
    start: time = time(9, 0),
) -> Intervention:
    """Build a scheduled visit.

    Args:
        customer_id (str): The household it is delivered to.
        visit_id (str): The identifier to assign.
        start (time): When it begins.

    Returns:
        Intervention: The visit.
    """
    return Intervention(
        company_id="company-1",
        team_id="team-1",
        id=visit_id,
        planning_run_id="run-1",
        name="Toilette matin",
        intervention_type_id="type-1",
        quote_line_id="line-1",
        hca_id="hca-1",
        hca_full_name="Luc Martin",
        customer_id=customer_id,
        day=MONDAY,
        start_time=start,
        end_time=time(start.hour + 1, 0),
        address=ADDRESS,
        status=InterventionStatus.PLANNED,
    )


@pytest.fixture
def interventions() -> AsyncMock:
    """Return a stand-in intervention repository.

    Returns:
        AsyncMock: The repository double.
    """
    repository = AsyncMock()
    repository.list_for_customer.return_value = [_visit()]
    repository.list_for_customers.return_value = [_visit()]
    repository.list_customer_ids_for_period.return_value = ["customer-1"]
    return repository


@pytest.fixture
def customers() -> AsyncMock:
    """Return a stand-in customer repository.

    Returns:
        AsyncMock: The repository double.
    """
    repository = AsyncMock()
    repository.get.return_value = _household()
    repository.list_by_ids.return_value = [_household()]
    repository.portfolio_ids.return_value = ["customer-1"]
    repository.is_served_by.return_value = True
    return repository


def _unscoped_teams() -> AsyncMock:
    """Return a team-service double that narrows nothing.

    Returns:
        AsyncMock: The double, answering ``None`` to every scope question.
    """
    stub = AsyncMock()
    stub.readable_team_ids.return_value = None
    stub.readable_hca_ids.return_value = None
    stub.readable_customer_ids.return_value = None
    return stub


@pytest.fixture
def service(interventions: AsyncMock, customers: AsyncMock) -> PlanningService:
    """Return a planning service over stand-in repositories.

    Args:
        interventions (AsyncMock): The intervention repository double.
        customers (AsyncMock): The customer repository double.

    Returns:
        PlanningService: The service under test.
    """
    return PlanningService(
        runs=AsyncMock(),
        interventions=interventions,
        quotes=AsyncMock(),
        customers=customers,
        hcas=AsyncMock(),
        types=AsyncMock(),
        settings=AsyncMock(),
        # Unscoped: `None` means every team, which is an administrator's answer
        # and what these whole-agency assertions were written against.
        teams=_unscoped_teams(),
        config=PlanningConfig(),
    )


class TestWhoMayReadAHouseholdsCare:
    """Tests for the authorisation on the customers planning."""

    @pytest.mark.parametrize(
        "role",
        [
            pytest.param(UserRole.MANAGER, id="A manager"),
            pytest.param(UserRole.ADMIN, id="An administrator"),
        ],
    )
    async def test_a_supervisor_reads_any_household(
        self, service: PlanningService, customers: AsyncMock, role: UserRole
    ) -> None:
        """They run the agency, so every household's care is theirs to see."""
        planning = await service.planning_for_customer(
            "customer-1", _user(role), MONDAY, SUNDAY
        )

        assert planning.customer_full_name == "Marie Durand"
        assert len(planning.interventions) == 1
        customers.is_served_by.assert_not_awaited()

    async def test_an_assistant_reads_a_household_they_serve(
        self, service: PlanningService, customers: AsyncMock
    ) -> None:
        """**Checked against the portfolio, with both identifiers.**

        Notes:
            A quote records the *account* that wrote it rather than the
            assistant, so passing the assistant's identifier for both quietly
            halves the portfolio — the household they quoted last week would
            disappear from their own screen.
        """
        caller = _user(UserRole.HCA, hca_id="hca-1")

        await service.planning_for_customer("customer-1", caller, MONDAY, SUNDAY)

        customers.is_served_by.assert_awaited_once_with(
            "customer-1", "hca-1", caller.id
        )

    async def test_a_household_outside_the_portfolio_is_not_found(
        self, service: PlanningService, customers: AsyncMock
    ) -> None:
        """**404, not 403 — and that is a security decision.**

        Notes:
            Answering "not yours" would confirm the household exists. Repeated
            over an identifier space that is most of what a customer list is
            worth, that is the enumeration the agency's book is protected from.
        """
        customers.is_served_by.return_value = False

        with pytest.raises(MTPlanningCustomerNotFound):
            await service.planning_for_customer(
                "customer-9", _user(UserRole.HCA, hca_id="hca-1"), MONDAY, SUNDAY
            )

    async def test_an_absent_household_answers_the_same_way(
        self, service: PlanningService, customers: AsyncMock
    ) -> None:
        """Absent and not-yours are indistinguishable from the outside."""
        customers.get.return_value = None

        with pytest.raises(MTPlanningCustomerNotFound):
            await service.planning_for_customer(
                "ghost", _user(UserRole.MANAGER), MONDAY, SUNDAY
            )

    async def test_an_assistant_with_no_record_is_refused(
        self, service: PlanningService
    ) -> None:
        """**Defence in depth, and the only way to reach it is to force it.**

        Notes:
            `User` already refuses to build an assistant account with no
            assistant record, so this branch cannot be reached through the door.
            It is still worth having and worth testing: the service must not
            assume a model invariant it does not own, and without the guard a
            relaxed invariant would send ``None`` to the portfolio query, which
            answers "no households" — an assistant with an empty screen and
            nothing saying why. `model_construct` skips the validators precisely
            so the branch can be exercised.
        """
        caller = User.model_construct(
            company_id="company-1",
            id="user-hca",
            email="hca@example.com",
            full_name="Test Hca",
            hashed_password="$2b$12$" + "a" * 53,
            role=UserRole.HCA,
            hca_id=None,
        )

        with pytest.raises(MTPlanningForbidden):
            await service.planning_for_customer("customer-1", caller, MONDAY, SUNDAY)

    @pytest.mark.parametrize(
        "method",
        [
            pytest.param("planning_for_customer", id="One household"),
            pytest.param("customer_plannings", id="Every household"),
        ],
    )
    async def test_a_household_account_is_refused_with_403_not_422(
        self, service: PlanningService, method: str
    ) -> None:
        """**The trap the sibling assistants route falls into.**

        Notes:
            `UserRole.rank` refuses to rank a customer — there is no number that
            is correct for an axis rather than a rung — and the refusal surfaces
            as a 422 whose body discusses role ladders. A household reaching a
            staff route is not sending a malformed request. It is asking for
            something that is not theirs. Testing for
            :class:`MTPlanningForbidden` is what pins the 403, because the wrong
            answer here is not an exception nobody notices — it is a plausible
            one.
        """
        caller = _user(UserRole.CUSTOMER, customer_id="customer-1")
        arguments = (
            ("customer-1", caller, MONDAY, SUNDAY)
            if method == "planning_for_customer"
            else (caller, MONDAY, SUNDAY)
        )

        with pytest.raises(MTPlanningForbidden):
            await getattr(service, method)(*arguments)


class TestTheWholeAgencysCare:
    """Tests for the collection, and what it costs."""

    async def test_a_manager_sees_every_household_with_care(
        self, service: PlanningService, interventions: AsyncMock
    ) -> None:
        """Read off the visits, not off the customer book."""
        plannings = await service.customer_plannings(
            _user(UserRole.MANAGER), MONDAY, SUNDAY
        )

        assert [planning.customer_id for planning in plannings] == ["customer-1"]
        # The third argument is the caller's team scope, applied in the
        # statement rather than to the page. `None` is an administrator's answer
        # and what the unscoped double here returns.
        interventions.list_customer_ids_for_period.assert_awaited_once_with(
            MONDAY, SUNDAY, None
        )

    async def test_an_assistant_sees_only_their_portfolio(
        self, service: PlanningService, customers: AsyncMock, interventions: AsyncMock
    ) -> None:
        """**Scoped in the statement, never by filtering afterwards.**

        Notes:
            A list built wide and narrowed in Python has already read the
            addresses and schedules of households this assistant is not
            entitled to.
        """
        caller = _user(UserRole.HCA, hca_id="hca-1")

        await service.customer_plannings(caller, MONDAY, SUNDAY)

        customers.portfolio_ids.assert_awaited_once_with("hca-1", caller.id)
        interventions.list_customer_ids_for_period.assert_not_awaited()

    async def test_the_whole_agency_costs_three_queries(
        self, service: PlanningService, customers: AsyncMock, interventions: AsyncMock
    ) -> None:
        """**Not one per household, which is the point of the batched read.**

        Notes:
            Written as a loop over households, a manager with four hundred of
            them would hold a connection for eight hundred round trips — on the
            screen an assistant now lands on every morning. The count is
            asserted rather than described, because "it batches" is the kind of
            claim a later refactor quietly falsifies.
        """
        interventions.list_customer_ids_for_period.return_value = [
            "customer-1",
            "customer-2",
            "customer-3",
        ]
        customers.list_by_ids.return_value = [
            _household("customer-1"),
            _household("customer-2", "Bernard"),
            _household("customer-3", "Charpentier"),
        ]

        await service.customer_plannings(_user(UserRole.MANAGER), MONDAY, SUNDAY)

        assert interventions.list_for_customers.await_count == 1
        assert customers.list_by_ids.await_count == 1
        assert interventions.list_for_customer.await_count == 0
        assert customers.get.await_count == 0

    async def test_the_visits_are_grouped_under_their_own_household(
        self, service: PlanningService, customers: AsyncMock, interventions: AsyncMock
    ) -> None:
        """One read, split by household — the grouping must not cross over."""
        interventions.list_customer_ids_for_period.return_value = [
            "customer-1",
            "customer-2",
        ]
        customers.list_by_ids.return_value = [
            _household("customer-1"),
            _household("customer-2", "Bernard"),
        ]
        interventions.list_for_customers.return_value = [
            _visit("customer-1", "visit-1"),
            _visit("customer-2", "visit-2"),
            _visit("customer-2", "visit-3", start=time(14, 0)),
        ]

        plannings = await service.customer_plannings(
            _user(UserRole.MANAGER), MONDAY, SUNDAY
        )

        by_id = {planning.customer_id: planning for planning in plannings}
        assert [v.id for v in by_id["customer-1"].interventions] == ["visit-1"]
        assert [v.id for v in by_id["customer-2"].interventions] == [
            "visit-2",
            "visit-3",
        ]

    async def test_a_household_with_no_visit_is_still_listed(
        self, service: PlanningService, customers: AsyncMock, interventions: AsyncMock
    ) -> None:
        """**An assistant's portfolio is not the same set as "has work".**

        Notes:
            A household they quoted but have not yet visited belongs on their
            rail with an empty week. Dropping it would make the screen disagree
            with their own customer list, which is built from the same
            portfolio.
        """
        caller = _user(UserRole.HCA, hca_id="hca-1")
        customers.portfolio_ids.return_value = ["customer-1", "customer-2"]
        customers.list_by_ids.return_value = [
            _household("customer-1"),
            _household("customer-2", "Bernard"),
        ]
        interventions.list_for_customers.return_value = [_visit("customer-1")]

        plannings = await service.customer_plannings(caller, MONDAY, SUNDAY)

        empty = [p for p in plannings if p.customer_id == "customer-2"]
        assert empty and empty[0].interventions == []

    async def test_an_empty_portfolio_reads_nothing(
        self, service: PlanningService, customers: AsyncMock, interventions: AsyncMock
    ) -> None:
        """A new assistant's first day is an empty screen, not a query storm."""
        customers.portfolio_ids.return_value = []

        plannings = await service.customer_plannings(
            _user(UserRole.HCA, hca_id="hca-1"), MONDAY, SUNDAY
        )

        assert plannings == []
        interventions.list_for_customers.assert_not_awaited()
        customers.list_by_ids.assert_not_awaited()
