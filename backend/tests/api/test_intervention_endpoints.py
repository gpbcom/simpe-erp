from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import Optional
from unittest.mock import AsyncMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_event_publisher,
    get_intervention_service,
    get_manager_user,
    get_planning_service,
)
from api.exception_handlers import ExceptionHandlers
from api.v1.planning.interventions import router as interventions_router
from models.auth.user import User
from models.enums import PlanningRunStatus, QuoteStatus, ServiceCategory, UserRole
from models.planning.planning_run import PlanningRun
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from service.intervention_types.exceptions import MTInterventionTypeNotFound
from service.planning.exceptions import (
    MTInterventionNotFound,
    MTInterventionNotQuoted,
)

MONDAY = "2026-08-03"
SUNDAY = "2026-08-09"
PERIOD = {"period_start": MONDAY, "period_end": SUNDAY}
VISIT = "/api/v1/planning/interventions/visit-1"


def _user(role: UserRole = UserRole.MANAGER) -> User:
    """Build an account for a role.

    Args:
        role (UserRole): The role to grant.

    Returns:
        User: The account.
    """
    return User(
        company_id="company-1",
        id=f"user-{role.value}",
        email=f"{role.value}@example.com",
        full_name="Test Account",
        role=role,
    )


def _run() -> PlanningRun:
    """Build a pending planning run.

    Returns:
        PlanningRun: The run.
    """
    return PlanningRun(
        company_id="company-1",
        team_id="team-1",
        id="run-1",
        status=PlanningRunStatus.PENDING,
        requested_by="user-manager",
        period_start=date(2026, 8, 3),
        period_end=date(2026, 8, 9),
    )


def _quote() -> Quote:
    """Build a one-line quote.

    Returns:
        Quote: The quote.
    """
    return Quote(
        company_id="company-1",
        team_id="team-1",
        id="quote-1",
        reference="D-2601",
        customer_id="customer-1",
        status=QuoteStatus.DRAFT,
        lines=[
            QuoteLine(
                id="line-1",
                name="Compagnie",
                intervention_type_id="type-comfort",
                service_category=ServiceCategory.COMFORT,
                service_date=date(2026, 8, 3),
                earliest_start=time(9, 0),
                latest_end=time(13, 0),
                duration_minutes=120,
            )
        ],
    )


def _client(
    interventions: AsyncMock,
    plannings: AsyncMock,
    caller: Optional[User] = None,
) -> TestClient:
    """Build a client over the intervention router alone.

    Args:
        interventions (AsyncMock): The stubbed intervention service.
        plannings (AsyncMock): The stubbed planning service.
        caller (Optional[User]): The account the request is authenticated as.

    Returns:
        TestClient: The client.

    Notes:
        The publisher is overridden as well as the services. Left real it would
        try to reach a broker that is not running, and every 202 would spend
        its connect timeout before answering — a hermetic suite that waits on
        the network is not hermetic, it is slow and flaky.
    """
    app = FastAPI()
    app.include_router(interventions_router)
    ExceptionHandlers().register(app)
    publisher = AsyncMock()
    publisher.publish.return_value = True
    app.dependency_overrides[get_intervention_service] = lambda: interventions
    app.dependency_overrides[get_planning_service] = lambda: plannings
    app.dependency_overrides[get_event_publisher] = lambda: publisher
    app.dependency_overrides[get_manager_user] = lambda: caller if caller else _user()
    return TestClient(app)


@pytest.fixture
def interventions() -> AsyncMock:
    """Return a stubbed intervention service.

    Returns:
        AsyncMock: The service double.
    """
    stub = AsyncMock()
    # The team travels back with the quote: a cancellation ends in a replan
    # of one team's week, and the row is gone by the time anybody could ask.
    stub.delete.return_value = ("team-1", _quote())
    stub.change_type.return_value = _quote()
    return stub


@pytest.fixture
def plannings() -> AsyncMock:
    """Return a stubbed planning service.

    Returns:
        AsyncMock: The service double.
    """
    stub = AsyncMock()
    stub.request_run.return_value = _run()
    stub.queue_replan.return_value = [_run()]
    return stub


class TestCancellingAVisit:
    """Tests for ``DELETE /planning/interventions/{id}``."""

    def test_it_answers_202_with_the_replan(
        self, interventions: AsyncMock, plannings: AsyncMock
    ) -> None:
        """The quote is already changed; the calendar catches up on a worker."""
        response = _client(interventions, plannings).delete(VISIT, params=PERIOD)

        assert response.status_code == 202
        assert response.json()["id"] == "run-1"

    def test_it_replans_the_window_it_was_given(
        self, interventions: AsyncMock, plannings: AsyncMock
    ) -> None:
        """The span on screen, not one invented here.

        Notes:
            Replanning a different period than the one the manager is looking
            at leaves them comparing two answers to the same question.
        """
        _client(interventions, plannings).delete(VISIT, params=PERIOD)

        assert plannings.queue_replan.await_args.kwargs["period"] == (
            date(2026, 8, 3),
            date(2026, 8, 9),
        )
        # Exactly the one team whose calendar held the cancelled visit.
        assert plannings.queue_replan.await_args.kwargs["team_ids"] == ["team-1"]

    def test_a_backwards_period_is_refused_before_anything_is_deleted(
        self, interventions: AsyncMock, plannings: AsyncMock
    ) -> None:
        """422, and the visit is still there."""
        response = _client(interventions, plannings).delete(
            VISIT, params={"period_start": SUNDAY, "period_end": MONDAY}
        )

        assert response.status_code == 422
        interventions.delete.assert_not_awaited()

    def test_an_unknown_visit_answers_404(
        self, interventions: AsyncMock, plannings: AsyncMock
    ) -> None:
        """Mapped by the handler table, not by the endpoint."""
        interventions.delete.side_effect = MTInterventionNotFound("gone")

        response = _client(interventions, plannings).delete(VISIT, params=PERIOD)

        assert response.status_code == 404

    def test_a_visit_whose_line_has_vanished_answers_409(
        self, interventions: AsyncMock, plannings: AsyncMock
    ) -> None:
        """A conflict, not a validation error: the request was well formed."""
        interventions.delete.side_effect = MTInterventionNotQuoted("no line")

        response = _client(interventions, plannings).delete(VISIT, params=PERIOD)

        assert response.status_code == 409

    def test_a_quote_deleted_with_its_last_line_still_answers_202(
        self, interventions: AsyncMock, plannings: AsyncMock
    ) -> None:
        """The service reports "no quote left"; the replan is still queued."""
        interventions.delete.return_value = ("team-1", None)

        response = _client(interventions, plannings).delete(VISIT, params=PERIOD)

        assert response.status_code == 202


class TestSellingAVisitAsSomethingElse:
    """Tests for ``PATCH /planning/interventions/{id}/type``."""

    def test_it_answers_the_repriced_quote(
        self, interventions: AsyncMock, plannings: AsyncMock
    ) -> None:
        """So the caller sees the new totals without a second request."""
        response = _client(interventions, plannings).patch(
            f"{VISIT}/type", json={"intervention_type_id": "type-comfort"}
        )

        assert response.status_code == 200
        assert response.json()["reference"] == "D-2601"

    def test_it_passes_the_chosen_type_through(
        self, interventions: AsyncMock, plannings: AsyncMock
    ) -> None:
        """The payload is the whole request."""
        _client(interventions, plannings).patch(
            f"{VISIT}/type", json={"intervention_type_id": "type-comfort"}
        )

        interventions.change_type.assert_awaited_once_with("visit-1", "type-comfort")

    def test_an_empty_type_is_refused(
        self, interventions: AsyncMock, plannings: AsyncMock
    ) -> None:
        """The request model refuses it before the service is reached."""
        response = _client(interventions, plannings).patch(
            f"{VISIT}/type", json={"intervention_type_id": "  "}
        )

        assert response.status_code == 422
        interventions.change_type.assert_not_awaited()

    def test_an_unknown_type_answers_404(
        self, interventions: AsyncMock, plannings: AsyncMock
    ) -> None:
        """The catalogue has no such entry."""
        interventions.change_type.side_effect = MTInterventionTypeNotFound("gone")

        response = _client(interventions, plannings).patch(
            f"{VISIT}/type", json={"intervention_type_id": "type-404"}
        )

        assert response.status_code == 404

    def test_it_does_not_replan(
        self, interventions: AsyncMock, plannings: AsyncMock
    ) -> None:
        """The hour costs something different; it happens at the same time.

        Notes:
            Every constraint the solver placed the visit under still holds, so
            a replan would reshuffle a dozen calendars to arrive at the same
            answer.
        """
        _client(interventions, plannings).patch(
            f"{VISIT}/type", json={"intervention_type_id": "type-comfort"}
        )

        plannings.queue_replan.assert_not_awaited()
