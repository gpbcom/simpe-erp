from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import List
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.configuration.planning_config import PlanningConfig
from models.enums import InterventionStatus, UserRole
from models.people.customer import Customer
from models.planning.intervention import Intervention
from service.customers.portal import CustomerPortalService
from service.planning.plannings import PlanningService

MONDAY = date(2026, 8, 3)
SUNDAY = date(2026, 8, 9)
HOUSEHOLD = "customer-1"
ADDRESS = {
    "street": "12 rue de Rivoli",
    "postal_code": "75004",
    "city": "Paris",
    "latitude": 48.8566,
    "longitude": 2.3522,
}


def _visit(
    visit_id: str,
    day: date = MONDAY,
    start: time = time(9, 0),
    status: InterventionStatus = InterventionStatus.PLANNED,
) -> Intervention:
    """Build a scheduled visit for the household under test.

    Args:
        visit_id (str): The identifier to assign.
        day (date): The day it happens.
        start (time): When it begins.
        status (InterventionStatus): Where it has reached.

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
        customer_id=HOUSEHOLD,
        day=day,
        start_time=start,
        end_time=time(start.hour + 1, 0),
        address=ADDRESS,
        status=status,
    )


def _household() -> Customer:
    """Build the household whose calendar both sides read.

    Returns:
        Customer: The household.
    """
    return Customer(
        id=HOUSEHOLD,
        first_name="Marie",
        last_name="Durand",
        phone_number="+33612345678",
        email="marie.durand@example.fr",
        address=ADDRESS,
    )


def _manager() -> User:
    """Build the staff account reading the agency's side.

    Returns:
        User: A manager.
    """
    return User(
        company_id="company-1",
        id="user-manager",
        email="manager@example.com",
        full_name="Test Manager",
        hashed_password="$2b$12$" + "a" * 53,
        role=UserRole.MANAGER,
    )


#: A week with something of every kind in it. **Cancelled and completed visits
#: are deliberately present**: neither side filters on status, and a test whose
#: fixture holds only planned visits would pass just as happily against a path
#: that had quietly started hiding them.
VISITS: List[Intervention] = [
    _visit("visit-1"),
    _visit("visit-2", start=time(14, 0), status=InterventionStatus.CANCELLED),
    _visit("visit-3", day=date(2026, 8, 5), status=InterventionStatus.COMPLETED),
]


@pytest.fixture
def intervention_store() -> AsyncMock:
    """Return the one repository both sides read through.

    Returns:
        AsyncMock: The repository double, shared by both services.

    Notes:
        **Shared on purpose.** The point of these tests is that the agency and
        the household are looking at one query rather than two that agree
        today, so both services are built over the *same* double and the double
        is the thing that answers.
    """
    store = AsyncMock()
    store.list_for_customer.return_value = list(VISITS)
    store.list_for_customers.return_value = list(VISITS)
    store.list_customer_ids_for_period.return_value = [HOUSEHOLD]
    return store


@pytest.fixture
def customers() -> AsyncMock:
    """Return a stand-in customer repository.

    Returns:
        AsyncMock: The repository double.
    """
    store = AsyncMock()
    store.get.return_value = _household()
    store.list_by_ids.return_value = [_household()]
    return store


@pytest.fixture
def staff(intervention_store: AsyncMock, customers: AsyncMock) -> PlanningService:
    """Return the service the agency's screen reads through.

    Args:
        intervention_store (AsyncMock): The shared repository double.
        customers (AsyncMock): The customer repository double.

    Returns:
        PlanningService: The service under test.
    """
    return PlanningService(
        runs=AsyncMock(),
        interventions=intervention_store,
        quotes=AsyncMock(),
        customers=customers,
        hcas=AsyncMock(),
        types=AsyncMock(),
        settings=AsyncMock(),
        teams=AsyncMock(),
        config=PlanningConfig(),
    )


@pytest.fixture
def portal(intervention_store: AsyncMock) -> CustomerPortalService:
    """Return the service the household's own screen reads through.

    Args:
        intervention_store (AsyncMock): The shared repository double.

    Returns:
        CustomerPortalService: The service under test.
    """
    return CustomerPortalService(
        customers=AsyncMock(),
        interventions=AsyncMock(),
        quotes=AsyncMock(),
        quote_store=AsyncMock(),
        intervention_store=intervention_store,
    )


class TestTheAgencyAndTheHouseholdSeeTheSameCare:
    """Tests for the one property this feature exists to have.

    Notes:
        A staff screen showing a household's calendar is worth having only if it
        is the calendar that household sees. "Synchronized" is not a promise
        anybody can keep by discipline — it is either one query or it is two
        that will disagree the first time somebody adds a filter to one of them.
        These tests are what fail when that happens.
    """

    async def test_one_household_reads_identically_on_both_sides(
        self, staff: PlanningService, portal: CustomerPortalService
    ) -> None:
        """**Element for element, and in the same order.**

        Notes:
            Equality of sets would pass a path that had started sorting
            differently, and a calendar rendered from a differently ordered list
            is a calendar with the afternoon visit drawn first.
        """
        agency = await staff.planning_for_customer(
            HOUSEHOLD, _manager(), MONDAY, SUNDAY
        )
        household = await portal.planning(HOUSEHOLD, MONDAY, SUNDAY)

        assert agency.interventions == household
        assert [visit.id for visit in agency.interventions] == [
            visit.id for visit in household
        ]

    async def test_both_sides_ask_the_same_question(
        self,
        staff: PlanningService,
        portal: CustomerPortalService,
        intervention_store: AsyncMock,
    ) -> None:
        """**The same method, with the same arguments, on both paths.**

        Notes:
            This is the structural half of the guarantee. The test above would
            still pass if one side started post-filtering a wider read; this one
            pins the read itself, so a second query introduced on either side is
            a failure here rather than a discrepancy somebody notices on the
            telephone.
        """
        await staff.planning_for_customer(HOUSEHOLD, _manager(), MONDAY, SUNDAY)
        staff_call = intervention_store.list_for_customer.await_args

        intervention_store.list_for_customer.reset_mock()
        await portal.planning(HOUSEHOLD, MONDAY, SUNDAY)
        portal_call = intervention_store.list_for_customer.await_args

        assert staff_call == portal_call

    async def test_neither_side_hides_a_cancelled_visit(
        self, staff: PlanningService, portal: CustomerPortalService
    ) -> None:
        """**A cancelled visit is a fact both parties need.**

        Notes:
            A family rings about a visit that did not happen; a manager who
            cannot see it on the same screen cannot answer. Neither side filters
            on status, and this is where that stays true — the fixture carries a
            cancelled and a completed visit precisely so a status filter added
            to either path fails here.
        """
        agency = await staff.planning_for_customer(
            HOUSEHOLD, _manager(), MONDAY, SUNDAY
        )
        household = await portal.planning(HOUSEHOLD, MONDAY, SUNDAY)
        cancelled = InterventionStatus.CANCELLED

        assert any(visit.status is cancelled for visit in agency.interventions)
        assert any(visit.status is cancelled for visit in household)

    async def test_the_batched_read_agrees_with_the_household_too(
        self, staff: PlanningService, portal: CustomerPortalService
    ) -> None:
        """**The collection is where batching could break the agreement.**

        Notes:
            The whole-agency screen reads every household in one statement
            rather than one at a time, which is the difference between three
            queries and eight hundred. That optimisation is only safe if the
            batched read returns exactly what the single read returns — so the
            comparison is made against the *household's own* service, not
            against the single-household staff method, which would only prove
            the two staff paths agree with each other.
        """
        agency = await staff.customer_plannings(_manager(), MONDAY, SUNDAY)
        household = await portal.planning(HOUSEHOLD, MONDAY, SUNDAY)

        mine = [entry for entry in agency if entry.customer_id == HOUSEHOLD]
        assert len(mine) == 1
        assert mine[0].interventions == household
