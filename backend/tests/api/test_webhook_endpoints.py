from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Iterator
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_customer_service,
    get_email_service,
    get_hca_service,
    get_planning_service,
    get_quote_service,
    get_user_repository,
)
from api.exception_handlers import ExceptionHandlers
from api.middleware.auth_middleware import AuthMiddleware
from api.v1.webhooks.webhooks import router as webhooks_router
from models.auth.user import User
from models.enums import PlanningRunStatus, UserRole
from models.planning.planning_run import PlanningRun
from service.planning.exceptions import MTPlanningRunNotFound

TOKEN = "a-shared-secret"


@pytest.fixture(autouse=True)
def configured_token(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Put the webhook secret in the environment for the whole module.

    Args:
        monkeypatch (pytest.MonkeyPatch): Used to set the variable.

    Yields:
        None: While the secret is set.

    Notes:
        The application configuration is cached, so the *value* is read from
        the environment at call time by design — that is what lets the secret
        be rotated without a restart, and what lets this fixture work.
    """
    monkeypatch.setenv("PLANNING_WEBHOOK_TOKEN", TOKEN)
    yield


@pytest.fixture
def emails() -> MagicMock:
    """Return a stubbed email service.

    Returns:
        MagicMock: A service that reports two plannings and one quote sent.
    """
    service = MagicMock()
    service.send_plannings = AsyncMock(return_value=2)
    service.send_quotes = AsyncMock(return_value=1)
    return service


@pytest.fixture
def client(emails: MagicMock) -> TestClient:
    """Return a client over the webhook router alone.

    Args:
        emails (MagicMock): The stubbed email service.

    Returns:
        TestClient: A client with every collaborator replaced.
    """
    plannings = MagicMock()
    plannings.get_run = AsyncMock(
        return_value=PlanningRun(
            id="run-1",
            requested_by="admin@example.com",
            period_start=date(2026, 8, 3),
            period_end=date(2026, 8, 9),
            status=PlanningRunStatus.SUCCEEDED,
        )
    )
    plannings.all_plannings = AsyncMock(return_value=[])
    hcas = MagicMock()
    hcas.list = AsyncMock(return_value=[])
    quotes = MagicMock()
    quotes.list = AsyncMock(return_value=[])
    customers = MagicMock()
    customers.list = AsyncMock(return_value=[])
    # The repository is overridden too: the endpoint reads the managers and
    # administrators who receive the consolidated copy, and an unmocked
    # repository would try to open a real connection.
    users = MagicMock()
    users.list = AsyncMock(return_value=[])
    # The webhook resolves the run's requester so the documents it sends
    # are attributed to that account's agency, rather than to a synthetic
    # caller belonging to none.
    users.get = AsyncMock(
        return_value=User(
            id="user-admin",
            email="admin@example.com",
            full_name="Camille Fournier",
            role=UserRole.ADMIN,
            company_id="company-1",
        )
    )

    app = FastAPI()
    app.include_router(webhooks_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_email_service] = lambda: emails
    app.dependency_overrides[get_planning_service] = lambda: plannings
    app.dependency_overrides[get_hca_service] = lambda: hcas
    app.dependency_overrides[get_quote_service] = lambda: quotes
    app.dependency_overrides[get_customer_service] = lambda: customers
    app.dependency_overrides[get_user_repository] = lambda: users
    return TestClient(app, raise_server_exceptions=False)


class TestPlanningCompletedWebhook:
    """Tests for the endpoint that dispatches a finished planning."""

    def test_a_valid_call_reports_what_it_sent(
        self, client: TestClient, emails: MagicMock
    ) -> None:
        """The answer carries counts, not a bare acknowledgement."""
        response = client.post(
            "/api/v1/webhooks/planning-completed",
            json={"run_id": "run-1"},
            headers={"X-Webhook-Token": TOKEN},
        )
        assert response.status_code == 200
        assert response.json() == {
            "run_id": "run-1",
            "plannings_sent": 2,
            "quotes_sent": 1,
        }
        emails.send_plannings.assert_awaited_once()
        emails.send_quotes.assert_awaited_once()

    def test_a_call_without_the_secret_is_refused(
        self, client: TestClient, emails: MagicMock
    ) -> None:
        """The endpoint is outside the bearer middleware, so this is the guard."""
        response = client.post(
            "/api/v1/webhooks/planning-completed", json={"run_id": "run-1"}
        )
        assert response.status_code == 401
        emails.send_plannings.assert_not_awaited()

    def test_a_wrong_secret_is_refused(
        self, client: TestClient, emails: MagicMock
    ) -> None:
        """A near-miss is as good as nothing."""
        response = client.post(
            "/api/v1/webhooks/planning-completed",
            json={"run_id": "run-1"},
            headers={"X-Webhook-Token": TOKEN + "x"},
        )
        assert response.status_code == 401
        emails.send_quotes.assert_not_awaited()

    def test_the_refusal_says_nothing_about_the_secret(
        self, client: TestClient
    ) -> None:
        """A 401 that describes the mismatch helps whoever is guessing."""
        response = client.post(
            "/api/v1/webhooks/planning-completed",
            json={"run_id": "run-1"},
            headers={"X-Webhook-Token": "wrong"},
        )
        assert response.json()["detail"] == "This webhook requires a shared secret."

    def test_an_empty_run_id_is_rejected(self, client: TestClient) -> None:
        """The payload is validated by its own request model."""
        response = client.post(
            "/api/v1/webhooks/planning-completed",
            json={"run_id": "   "},
            headers={"X-Webhook-Token": TOKEN},
        )
        assert response.status_code == 422

    def test_an_unknown_run_answers_404(
        self, client: TestClient, emails: MagicMock
    ) -> None:
        """The service's own exception reaches the app-wide handler."""
        overrides = client.app.dependency_overrides
        plannings = overrides[get_planning_service]()
        plannings.get_run = AsyncMock(
            side_effect=MTPlanningRunNotFound("No planning run 'x' exists.")
        )
        response = client.post(
            "/api/v1/webhooks/planning-completed",
            json={"run_id": "x"},
            headers={"X-Webhook-Token": TOKEN},
        )
        assert response.status_code == 404
        emails.send_plannings.assert_not_awaited()


class TestWebhookExemption:
    """Tests for the authentication middleware's exemption."""

    def test_the_webhook_prefix_is_exempt_from_the_bearer_guard(self) -> None:
        """A webhook has no signed-in user, so it cannot carry a bearer token.

        Notes:
            Without the exemption the middleware answers 401 before the
            endpoint ever compares the shared secret, and the dispatch can
            never run.
        """
        assert "/api/v1/webhooks/" in AuthMiddleware.EXEMPT_PATHS
