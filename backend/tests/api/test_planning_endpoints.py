from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import List, Optional
from unittest.mock import AsyncMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.dependencies import (
    get_admin_user,
    get_manager_user,
    get_current_user,
    get_planning_service,
)
from api.exception_handlers import ExceptionHandlers
from api.v1.planning.plannings import router as plannings_router

# First-party imports
import api.v1.planning.runs as runs_module
from api.v1.planning.runs import router as runs_router
from models.auth.user import User
from models.enums import InterventionStatus, PlanningRunStatus, UserRole
from models.planning.customer_planning import CustomerPlanning
from models.planning.hca_planning import HcaPlanning
from models.planning.intervention import Intervention
from models.planning.planning_run import PlanningRun
from service.planning.exceptions import (
    MTPlanningCustomerNotFound,
    MTPlanningForbidden,
    MTPlanningRunNotFound,
)

MONDAY = "2026-08-03"
SUNDAY = "2026-08-09"
PERIOD = {"period_start": MONDAY, "period_end": SUNDAY}


def _user(role: UserRole = UserRole.ADMIN, hca_id: Optional[str] = None) -> User:
    """Build an account for a role.

    Args:
        role (UserRole): The role to grant.
        hca_id (Optional[str]): The assistant record it is bound to, if any.

    Returns:
        User: The account.
    """
    return User(
        company_id="company-1",
        id=f"user-{role.value}",
        email=f"{role.value}@example.com",
        full_name="Test Account",
        role=role,
        hca_id=hca_id if hca_id else ("hca-1" if role is UserRole.HCA else None),
    )


def _run(status: PlanningRunStatus = PlanningRunStatus.PENDING) -> PlanningRun:
    """Build a planning run.

    Args:
        status (PlanningRunStatus): Where the run is in its lifecycle.

    Returns:
        PlanningRun: The run.
    """
    return PlanningRun(
        company_id="company-1",
        team_id="team-1",
        id="run-1",
        status=status,
        requested_by="user-admin",
        period_start=date(2026, 8, 3),
        period_end=date(2026, 8, 9),
    )


def _planning(hca_id: str = "hca-1") -> HcaPlanning:
    """Build a one-visit diary.

    Args:
        hca_id (str): Whose diary it is.

    Returns:
        HcaPlanning: The diary.
    """
    return HcaPlanning(
        hca_id=hca_id,
        hca_full_name="Luc Martin",
        period_start=date(2026, 8, 3),
        period_end=date(2026, 8, 9),
        interventions=[
            Intervention(
                company_id="company-1",
                team_id="team-1",
                id="visit-1",
                planning_run_id="run-1",
                name="Toilette matin",
                intervention_type_id="type-1",
                quote_line_id="line-1",
                hca_id=hca_id,
                hca_full_name="Luc Martin",
                customer_id="customer-1",
                day=date(2026, 8, 3),
                start_time=time(9, 0),
                end_time=time(11, 0),
                address={
                    "street": "12 rue de Rivoli",
                    "postal_code": "75004",
                    "city": "Paris",
                },
                status=InterventionStatus.PLANNED,
            )
        ],
    )


async def _no_background_job(run_id: str) -> None:
    """Stand in for the background solve.

    Args:
        run_id (str): The run that would have been executed.
    """


def _client(service: AsyncMock, caller: User) -> TestClient:
    """Build a client for the planning routers alone.

    Args:
        service (AsyncMock): The stubbed planning service.
        caller (User): The account the request is authenticated as.

    Returns:
        TestClient: A client over an app mounting only the routers under test.

    Notes:
        The production exception handlers are registered, because the routers
        deliberately raise domain exceptions rather than ``HTTPException`` —
        the status mapping lives in one table, not in each endpoint.

        The service goes through ``dependency_overrides``; the background job
        cannot, because it is handed to ``BackgroundTasks`` rather than
        resolved through ``Depends``, so it is replaced on the router module
        itself. Leaving the real one in place would have every 202 open its own
        database connection after the response — the client sees its 202, then
        the test blows up in the background task.

        The exception handlers are installed through the same registrar the
        application uses: the endpoints raise the service's own exceptions, so
        without them a refused planning answers 500 instead of 403 or 404.
    """
    runs_module.run_planning_job = _no_background_job
    app = FastAPI()
    app.include_router(runs_router)
    app.include_router(plannings_router)
    # The real handler set, not a stand-in: the routers let their domain
    # exceptions escape, so without it every refusal reads as a 500 here while
    # answering correctly in production.
    ExceptionHandlers().register(app)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_planning_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[get_admin_user] = lambda: caller
    # Requesting a planning is a manager's act now that a run rewrites one
    # team's week rather than the whole agency's.
    app.dependency_overrides[get_manager_user] = lambda: caller
    return TestClient(app)


@pytest.fixture
def service() -> AsyncMock:
    """Return a stubbed planning service.

    Returns:
        AsyncMock: The service double.
    """
    stub = AsyncMock()
    stub.request_run.return_value = _run()
    # One run per team: naming no team means "every team I run", so the route
    # answers with a list even when the caller runs exactly one.
    stub.teams_to_plan.return_value = ["team-1"]
    stub.queue_replan.return_value = [_run()]
    stub.run_for.return_value = _run(PlanningRunStatus.SUCCEEDED)
    stub.list_runs.return_value = [_run(PlanningRunStatus.SUCCEEDED)]
    stub.planning_for.return_value = _planning()
    stub.all_plannings.return_value = [_planning()]
    stub.planning_for_customer.return_value = _customer_planning()
    stub.customer_plannings.return_value = [_customer_planning()]
    return stub


class TestPlanningRunEndpoints:
    """Tests for starting and polling a planning computation."""

    # ------------------------------------------------------------------ #
    #  Starting a run
    # ------------------------------------------------------------------ #

    def test_starting_a_run_answers_202(self, service: AsyncMock) -> None:
        """The endpoint accepts the work rather than waiting for it.

        Notes:
            202, not 200: the solve runs for its configured budget on a worker
            thread, and holding the request open for it would tie up a
            connection and time the client out.
        """
        response = _client(service, _user()).post(
            "/api/v1/planning/runs", params=PERIOD
        )

        assert response.status_code == 202
        assert [run["id"] for run in response.json()] == ["run-1"]

    def test_the_response_carries_something_to_poll(self, service: AsyncMock) -> None:
        """A 202 with no identifier would be useless."""
        response = _client(service, _user()).post(
            "/api/v1/planning/runs", params=PERIOD
        )

        assert response.json()[0]["status"] == PlanningRunStatus.PENDING.value

    def test_the_requesting_admin_is_recorded(self, service: AsyncMock) -> None:
        """The run remembers who asked for it.

        Notes:
            A computation that rewrites every calendar for a week is worth
            attributing; without this the audit trail stops at "somebody".
        """
        _client(service, _user()).post("/api/v1/planning/runs", params=PERIOD)

        service.queue_replan.assert_awaited_once()
        assert service.queue_replan.await_args.kwargs["requested_by"] == "user-admin"

    def test_a_backwards_period_is_refused(self, service: AsyncMock) -> None:
        """An end before its start is rejected, not solved.

        Notes:
            Caught at the edge rather than in the solver: the solve would
            simply find no work and report a cheerful empty success, which
            looks identical to a quiet week.
        """
        response = _client(service, _user()).post(
            "/api/v1/planning/runs",
            params={"period_start": SUNDAY, "period_end": MONDAY},
        )

        assert response.status_code == 422
        service.queue_replan.assert_not_awaited()

    def test_a_missing_period_is_refused(self, service: AsyncMock) -> None:
        """Both bounds are required."""
        response = _client(service, _user()).post("/api/v1/planning/runs")

        assert response.status_code == 422

    # ------------------------------------------------------------------ #
    #  Polling a run
    # ------------------------------------------------------------------ #

    def test_polling_returns_the_run(self, service: AsyncMock) -> None:
        """The status endpoint reports where the run got to."""
        response = _client(service, _user()).get("/api/v1/planning/runs/run-1")

        assert response.status_code == 200
        assert response.json()["status"] == PlanningRunStatus.SUCCEEDED.value

    def test_polling_an_absent_run_is_404(self, service: AsyncMock) -> None:
        """An identifier that names nothing is not found."""
        service.run_for.side_effect = MTPlanningRunNotFound("no such run")

        response = _client(service, _user()).get("/api/v1/planning/runs/nope")

        assert response.status_code == 404

    def test_runs_can_be_listed(self, service: AsyncMock) -> None:
        """The run history is readable."""
        response = _client(service, _user()).get("/api/v1/planning/runs")

        assert response.status_code == 200
        assert len(response.json()) == 1


class TestPlanningReadEndpoints:
    """Tests for reading a diary through the API."""

    # ------------------------------------------------------------------ #
    #  Reading one diary
    # ------------------------------------------------------------------ #

    def test_an_assistant_reads_their_own_diary(self, service: AsyncMock) -> None:
        """The ordinary case answers 200 with the visits."""
        response = _client(service, _user(UserRole.HCA)).get(
            "/api/v1/planning/hcas/hca-1", params=PERIOD
        )

        assert response.status_code == 200
        assert response.json()["interventions"][0]["name"] == "Toilette matin"

    def test_reading_another_assistants_diary_is_403(self, service: AsyncMock) -> None:
        """The service's refusal surfaces as forbidden, not as a 500.

        Notes:
            This is the HTTP half of the confidentiality rule. The decision is
            the service's — the route cannot make it — and this pins that the
            answer reaching the caller is a 403 rather than an opaque error.
        """
        service.planning_for.side_effect = MTPlanningForbidden("not yours")

        response = _client(service, _user(UserRole.HCA)).get(
            "/api/v1/planning/hcas/hca-2", params=PERIOD
        )

        assert response.status_code == 403

    def test_an_absent_assistant_is_404(self, service: AsyncMock) -> None:
        """A diary for somebody who does not exist is not found."""
        service.planning_for.side_effect = MTPlanningRunNotFound("no such assistant")

        response = _client(service, _user(UserRole.MANAGER)).get(
            "/api/v1/planning/hcas/ghost", params=PERIOD
        )

        assert response.status_code == 404

    def test_the_caller_is_passed_to_the_service(self, service: AsyncMock) -> None:
        """The service receives who is asking, not just what they asked for.

        Notes:
            Without the caller the row-level check has nothing to compare
            against, so this pins the wiring the whole rule depends on.
        """
        caller = _user(UserRole.HCA)
        _client(service, caller).get("/api/v1/planning/hcas/hca-1", params=PERIOD)

        service.planning_for.assert_awaited_once()
        assert service.planning_for.await_args.args[1] is caller

    # ------------------------------------------------------------------ #
    #  Listing diaries
    # ------------------------------------------------------------------ #

    def test_listing_diaries_answers_200(self, service: AsyncMock) -> None:
        """A manager gets the workforce's calendars."""
        response = _client(service, _user(UserRole.MANAGER)).get(
            "/api/v1/planning/hcas", params=PERIOD
        )

        assert response.status_code == 200
        plannings: List[dict] = response.json()
        assert plannings[0]["hca_id"] == "hca-1"

    def test_an_unbound_assistant_listing_is_403(self, service: AsyncMock) -> None:
        """The service's refusal surfaces as forbidden here too."""
        service.all_plannings.side_effect = MTPlanningForbidden("no record")

        response = _client(service, _user(UserRole.HCA)).get(
            "/api/v1/planning/hcas", params=PERIOD
        )

        assert response.status_code == 403


class TestProductionRegistration:
    """Tests that the real application actually mounts these routes."""

    def test_the_planning_routes_are_mounted(self) -> None:
        """A router written but never included would pass every test above.

        Notes:
            The tests in this file build their own app, so they say nothing
            about production. This one reads the real application's route
            table.
        """
        from api.main import app

        paths = set(app.openapi()["paths"])

        assert "/api/v1/planning/runs" in paths
        assert "/api/v1/planning/runs/{run_id}" in paths
        assert "/api/v1/planning/hcas" in paths
        assert "/api/v1/planning/hcas/{hca_id}" in paths


def _customer_planning() -> CustomerPlanning:
    """Build one household's care as the service returns it.

    Returns:
        CustomerPlanning: The household's visits over the period.
    """
    return CustomerPlanning(
        customer_id="customer-1",
        customer_full_name="Marie Durand",
        period_start=date(2026, 8, 3),
        period_end=date(2026, 8, 9),
        interventions=[],
    )


class TestTheCustomersPlanning:
    """Tests for the two routes that read the calendar by household."""

    def test_every_household_is_listed_for_a_supervisor(
        self, service: AsyncMock
    ) -> None:
        """The whole-agency view, grouped by who receives the care."""
        response = _client(service, _user(UserRole.MANAGER)).get(
            "/api/v1/planning/customers", params=PERIOD
        )

        assert response.status_code == 200
        assert response.json()[0]["customer_full_name"] == "Marie Durand"

    def test_one_household_is_read_by_identifier(self, service: AsyncMock) -> None:
        """The narrowed view, for a family somebody is asking about."""
        response = _client(service, _user(UserRole.MANAGER)).get(
            "/api/v1/planning/customers/customer-1", params=PERIOD
        )

        assert response.status_code == 200
        assert response.json()["customer_id"] == "customer-1"

    def test_the_caller_reaches_the_service(self, service: AsyncMock) -> None:
        """**The row-level check needs to know who is asking.**

        Notes:
            A guard proves the caller is signed in; it cannot express "the
            households this assistant visits". Dropping the caller on the way
            through would leave the service scoping against nobody.
        """
        caller = _user(UserRole.HCA, hca_id="hca-1")

        _client(service, caller).get("/api/v1/planning/customers", params=PERIOD)

        assert service.customer_plannings.await_args.args[0] == caller

    def test_the_list_route_is_not_swallowed_by_its_sibling(
        self, service: AsyncMock
    ) -> None:
        """**A path-ordering hazard that is invisible until it bites.**

        Notes:
            FastAPI matches in declaration order, so a parametrised route
            declared ahead of its literal sibling swallows it — ``/customers``
            would arrive as a household named "customers". Asserted by the
            *service method* that was called, because both routes answer 200 and
            the wrong one would look entirely correct.
        """
        _client(service, _user(UserRole.MANAGER)).get(
            "/api/v1/planning/customers", params=PERIOD
        )

        service.customer_plannings.assert_awaited_once()
        service.planning_for_customer.assert_not_awaited()

    @pytest.mark.parametrize(
        "path",
        [
            pytest.param("/api/v1/planning/customers", id="Every household"),
            pytest.param("/api/v1/planning/customers/customer-1", id="One household"),
        ],
    )
    def test_a_period_is_required(self, service: AsyncMock, path: str) -> None:
        """A window nobody named is a read of everything ever planned."""
        response = _client(service, _user(UserRole.MANAGER)).get(path)

        assert response.status_code == 422

    def test_a_household_outside_the_portfolio_answers_404(
        self, service: AsyncMock
    ) -> None:
        """Not 403 — telling the two apart is what enables enumeration."""
        service.planning_for_customer.side_effect = MTPlanningCustomerNotFound(
            "no such household"
        )

        response = _client(service, _user(UserRole.HCA, hca_id="hca-1")).get(
            "/api/v1/planning/customers/customer-9", params=PERIOD
        )

        assert response.status_code == 404

    def test_a_household_account_is_refused_with_403(self, service: AsyncMock) -> None:
        """**And the body must not lecture them about role ladders.**

        Notes:
            The refusal comes from the service rather than a guard, so the wrong
            implementation answers 422 with the enumeration's internal
            explanation of why a customer cannot be ranked. That is both the
            wrong status and a leak of how the roles are modelled.
        """
        service.customer_plannings.side_effect = MTPlanningForbidden(
            "This planning is reserved for the agency's own staff."
        )

        response = _client(service, _user(UserRole.MANAGER)).get(
            "/api/v1/planning/customers", params=PERIOD
        )

        assert response.status_code == 403
        assert "ladder" not in response.text.lower()
