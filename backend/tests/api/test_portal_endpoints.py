from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Dict
from unittest.mock import AsyncMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_current_user,
    get_event_publisher,
    get_planning_service,
    get_customer_portal_service,
    get_customer_user,
    get_manager_user,
)
from api.exception_handlers import ExceptionHandlers
from api.v1.portal.portal import router as portal_router
from models.auth.user import User
from models.enums import Language, QuoteStatus, UserRole
from models.people.customer import Customer
from models.quoting.quote import Quote
from service.customers.exceptions import MTCustomerNotFound
from tests.annotations import ModelInput

CUSTOMER_PAYLOAD = {
    "first_name": "Marie",
    "last_name": "Durand",
    "phone_number": "+33612345678",
    "email": "marie.durand@example.com",
    "address": {
        "street": "12 rue de Rivoli",
        "postal_code": "75004",
        "city": "Paris",
    },
}


def _household() -> User:
    """Build the signed-in household's account.

    Returns:
        User: The account.
    """
    return User(
        company_id="company-1",
        id="user-customer",
        email="marie@example.com",
        full_name="Marie Durand",
        role=UserRole.CUSTOMER,
        customer_id="customer-1",
    )


def _client(portal: AsyncMock, plannings: AsyncMock = None) -> TestClient:
    """Build a client for the portal router alone.

    Args:
        portal (AsyncMock): The stubbed portal service.
        plannings (AsyncMock): The stubbed planning service. Defaults to one
            reporting that the household has no future visit, which is the
            no-replan path.

    Returns:
        TestClient: A client over an app mounting only the portal.

    Notes:
        ``get_customer_user`` is overridden so these tests need no
        authentication stack — which is exactly why the guard itself is
        asserted separately, on the router's own dependency graph.
    """
    app = FastAPI()
    app.include_router(portal_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_customer_portal_service] = lambda: portal
    app.dependency_overrides[get_customer_user] = _household
    app.dependency_overrides[get_current_user] = _household
    if plannings is None:
        plannings = AsyncMock()
        plannings.future_period_for_customer.return_value = None
    app.dependency_overrides[get_planning_service] = lambda: plannings
    app.dependency_overrides[get_event_publisher] = lambda: AsyncMock()
    return TestClient(app)


@pytest.fixture
def portal() -> AsyncMock:
    """Return a stubbed portal service.

    Returns:
        AsyncMock: The service double.
    """
    stub = AsyncMock()
    stub.profile.return_value = Customer(id="customer-1", **CUSTOMER_PAYLOAD)
    stub.update_profile.return_value = Customer(id="customer-1", **CUSTOMER_PAYLOAD)
    stub.planning.return_value = []
    stub.quotes_for.return_value = []
    awaiting = Quote(
        company_id="company-1",
        id="quote-1",
        reference="Q-2026-0001",
        customer_id="customer-1",
        status=QuoteStatus.PENDING_VALIDATION,
    )
    stub.cancel_visit.return_value = awaiting
    stub.reschedule_visit.return_value = awaiting
    stub.bills_for.return_value = []
    stub.bill_document.return_value = (b"%PDF-1.4 invoice", "F-2026-0042.pdf")
    stub.quote_document.return_value = (b"%PDF-1.4 quote", "Q-2026-0001.pdf")
    return stub


class TestPortalReads:
    """Tests for the household's read routes."""

    def test_the_profile_answers_200(self, portal: AsyncMock) -> None:
        """The ordinary case works."""
        response = _client(portal).get("/api/v1/portal/profile")

        assert response.status_code == 200
        assert response.json()["id"] == "customer-1"

    def test_the_household_is_taken_from_the_credential(
        self, portal: AsyncMock
    ) -> None:
        """**No route here accepts a customer identifier.**

        Notes:
            The whole space resolves the household from ``caller.customer_id``,
            so there is no parameter to point at somebody else's file. This
            asserts the value that actually reached the service.
        """
        _client(portal).get("/api/v1/portal/profile")

        portal.profile.assert_awaited_once_with("customer-1")

    def test_the_planning_requires_a_period(self, portal: AsyncMock) -> None:
        """An unbounded read would return every visit ever, to draw a week."""
        assert _client(portal).get("/api/v1/portal/planning").status_code == 422

    def test_the_planning_passes_its_period_through(self, portal: AsyncMock) -> None:
        """The calendar always knows which weeks it is showing."""
        response = _client(portal).get(
            "/api/v1/portal/planning?period_start=2026-09-01&period_end=2026-09-30"
        )

        assert response.status_code == 200
        assert portal.planning.await_args.args[0] == "customer-1"

    def test_the_quotes_answer_200(self, portal: AsyncMock) -> None:
        """Every quote ever written for them, unfiltered."""
        assert _client(portal).get("/api/v1/portal/quotes").status_code == 200


class TestPortalWrites:
    """Tests for what a household may change."""

    def test_the_contact_block_can_be_corrected(self, portal: AsyncMock) -> None:
        """The ordinary case works."""
        response = _client(portal).put("/api/v1/portal/profile", json=CUSTOMER_PAYLOAD)

        assert response.status_code == 200

    def test_a_status_in_the_payload_never_reaches_the_service(
        self, portal: AsyncMock
    ) -> None:
        """**The self-promotion attempt, refused by the payload's shape.**

        Notes:
            Honoured, a prospect could make themselves active and put their own
            work into the next planning run — the agency would be delivering
            care it never agreed to. The request model has no such field, so the
            value cannot be read back off it and cannot reach the customer.
        """
        _client(portal).put(
            "/api/v1/portal/profile",
            json={**CUSTOMER_PAYLOAD, "registration_status": "active"},
        )

        payload = portal.update_profile.await_args.args[1]
        assert not hasattr(payload, "registration_status")

    def test_an_empty_name_answers_422(self, portal: AsyncMock) -> None:
        """Half a name on an invoice is a call to the office."""
        response = _client(portal).put(
            "/api/v1/portal/profile", json={**CUSTOMER_PAYLOAD, "first_name": "  "}
        )

        assert response.status_code == 422

    def test_cancelling_a_visit_answers_200(self, portal: AsyncMock) -> None:
        """The quote comes back awaiting validation."""
        response = _client(portal).post(
            "/api/v1/portal/interventions/intervention-1/cancel"
        )

        assert response.status_code == 200
        assert response.json()["status"] == "pending-validation"

    def test_another_households_visit_answers_404(self, portal: AsyncMock) -> None:
        """404, not 403 — the two cases are indistinguishable on purpose."""
        portal.cancel_visit.side_effect = MTCustomerNotFound("no such visit")

        response = _client(portal).post(
            "/api/v1/portal/interventions/intervention-9/cancel"
        )

        assert response.status_code == 404

    def test_rescheduling_answers_200(self, portal: AsyncMock) -> None:
        """A day and a window move the visit and re-open the agreement."""
        response = _client(portal).post(
            "/api/v1/portal/interventions/intervention-1/reschedule",
            json={"day": "2026-09-15", "start_minute": 540, "end_minute": 720},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "pending-validation"

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param(
                {"day": "2026-09-15", "start_minute": 540, "end_minute": 540},
                id="an empty window",
            ),
            pytest.param(
                {"day": "2026-09-15", "start_minute": 720, "end_minute": 540},
                id="a backwards window",
            ),
            pytest.param({"start_minute": 540, "end_minute": 720}, id="no day"),
        ],
    )
    def test_an_impossible_window_answers_422(
        self, portal: AsyncMock, body: Dict[str, ModelInput]
    ) -> None:
        """Refused before the solver is asked to fit work into nothing.

        Args:
            portal (AsyncMock): The stubbed portal service.
            body (Dict[str, ModelInput]): The rejected payload.
        """
        response = _client(portal).post(
            "/api/v1/portal/interventions/intervention-1/reschedule", json=body
        )

        assert response.status_code == 422
        portal.reschedule_visit.assert_not_awaited()


class TestPortalGuard:
    """Tests for who may reach the space at all."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/portal/profile",
            "/api/v1/portal/planning",
            "/api/v1/portal/quotes",
            "/api/v1/portal/interventions/{intervention_id}/cancel",
            "/api/v1/portal/interventions/{intervention_id}/reschedule",
            "/api/v1/portal/quotes/{quote_id}/document",
            "/api/v1/portal/bills",
            "/api/v1/portal/bills/{bill_id}/document",
        ],
    )
    def test_every_route_is_behind_the_customer_guard(self, path: str) -> None:
        """**No route in this space is reachable by staff.**

        Args:
            path (str): The route under test.

        Notes:
            Asserted on the router's own dependency graph rather than through a
            request, because every test above overrides the guard — so none of
            them would notice it being dropped from one route. A household's
            calendar, address and telephone number are exactly what a guard
            forgotten on a single route would publish.
        """
        matching = [
            route
            for route in portal_router.routes
            if getattr(route, "path", None) == path
        ]
        assert matching, f"{path} is not on the portal router."

        for route in matching:
            guards = {
                dependency.call
                for dependency in route.dependant.dependencies
                if dependency.call is not None
            }
            assert get_customer_user in guards
            assert get_manager_user not in guards

    def test_the_portal_is_mounted(self) -> None:
        """A router written but never included would pass every test above."""
        from api.main import app

        paths = set(app.openapi()["paths"])

        assert "/api/v1/portal/profile" in paths
        assert "/api/v1/portal/planning" in paths


class TestPortalReplan:
    """Tests for the solve a household's change queues."""

    def test_cancelling_queues_a_replan(self, portal: AsyncMock) -> None:
        """**The most important side effect in the whole portal.**

        Notes:
            Without it the cancelled visit stays on an assistant's calendar
            until somebody starts a run by hand — and an assistant sent to a
            door for work the household withdrew is the worst outcome this
            feature can cause. Nothing looks wrong until it happens.
        """
        plannings = AsyncMock()
        plannings.future_period_for_customer.return_value = (
            date(2026, 9, 1),
            date(2026, 9, 30),
        )

        _client(portal, plannings=plannings).post(
            "/api/v1/portal/interventions/intervention-1/cancel"
        )

        plannings.queue_replan.assert_awaited_once()
        assert plannings.queue_replan.await_args.kwargs["period"] == (
            date(2026, 9, 1),
            date(2026, 9, 30),
        )

    def test_rescheduling_queues_a_replan(self, portal: AsyncMock) -> None:
        """Until one runs, the stored visit still names the old day."""
        plannings = AsyncMock()
        plannings.future_period_for_customer.return_value = (
            date(2026, 9, 1),
            date(2026, 9, 30),
        )

        _client(portal, plannings=plannings).post(
            "/api/v1/portal/interventions/intervention-1/reschedule",
            json={"day": "2026-09-15", "start_minute": 540, "end_minute": 720},
        )

        plannings.queue_replan.assert_awaited_once()

    def test_the_period_is_measured_before_the_change(self, portal: AsyncMock) -> None:
        """Afterwards the visit is gone and there is nothing left to measure.

        Notes:
            Measured after, the period would come back ``None`` for a household
            whose only visit was the cancelled one — and no replan would run, so
            every assistant left holding a gap would keep it.
        """
        order = []
        answered = portal.cancel_visit.return_value
        plannings = AsyncMock()
        # ``append`` answers None, so the ``or`` is what keeps each double
        # returning the value its caller actually needs.
        plannings.future_period_for_customer.side_effect = lambda _customer_id: (
            order.append("measured") or (date(2026, 9, 1), date(2026, 9, 30))
        )
        portal.cancel_visit.side_effect = lambda *_args: (
            order.append("cancelled") or answered
        )

        _client(portal, plannings=plannings).post(
            "/api/v1/portal/interventions/intervention-1/cancel"
        )

        assert order == ["measured", "cancelled"]

    def test_no_future_visit_queues_nothing(self, portal: AsyncMock) -> None:
        """There is no period to replan."""
        plannings = AsyncMock()
        plannings.future_period_for_customer.return_value = None

        _client(portal, plannings=plannings).post(
            "/api/v1/portal/interventions/intervention-1/cancel"
        )

        plannings.queue_replan.assert_not_awaited()

    def test_a_broker_failure_does_not_fail_the_household(
        self, portal: AsyncMock
    ) -> None:
        """**The change is already stored and correct by then.**

        Notes:
            Raising would report a failure for an operation that succeeded, and
            the household would press cancel again. The cost of swallowing it is
            a schedule that stays stale until the next run — logged at ERROR, so
            somebody can act on it.
        """
        plannings = AsyncMock()
        plannings.future_period_for_customer.return_value = (
            date(2026, 9, 1),
            date(2026, 9, 30),
        )
        plannings.queue_replan.side_effect = RuntimeError("broker unreachable")

        response = _client(portal, plannings=plannings).post(
            "/api/v1/portal/interventions/intervention-1/cancel"
        )

        assert response.status_code == 200


class TestPortalDocuments:
    """Tests for the two download buttons."""

    def test_a_quote_downloads_as_a_pdf(self, portal: AsyncMock) -> None:
        """The ordinary case works."""
        response = _client(portal).get("/api/v1/portal/quotes/quote-1/document")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF-")

    def test_the_filename_comes_from_the_server(self, portal: AsyncMock) -> None:
        """Never from anything the caller sends.

        Notes:
            The name is derived from the quote's own reference, so the route
            cannot be talked into writing outside it.
        """
        response = _client(portal).get("/api/v1/portal/quotes/quote-1/document")

        assert 'filename="Q-2026-0001.pdf"' in response.headers["content-disposition"]

    def test_a_quote_is_rendered_in_the_households_language(
        self, portal: AsyncMock
    ) -> None:
        """**The same offer, two readers.**

        Notes:
            A manager downloading it gets their own language; the household gets
            theirs. The language comes from the credential, so there is no
            parameter to disagree about it.
        """
        _client(portal).get("/api/v1/portal/quotes/quote-1/document")

        assert portal.quote_document.await_args.args[0] == "customer-1"
        assert portal.quote_document.await_args.args[2] is Language.FR

    def test_another_households_quote_answers_404(self, portal: AsyncMock) -> None:
        """Not 403 — the two cases stay indistinguishable."""
        portal.quote_document.side_effect = MTCustomerNotFound("no such quote")

        response = _client(portal).get("/api/v1/portal/quotes/quote-9/document")

        assert response.status_code == 404

    def test_the_invoices_answer_200(self, portal: AsyncMock) -> None:
        """Their own invoices, narrowed in the query."""
        response = _client(portal).get("/api/v1/portal/bills")

        assert response.status_code == 200
        assert portal.bills_for.await_args.args == ("customer-1", "company-1")

    def test_an_invoice_downloads_as_a_pdf(self, portal: AsyncMock) -> None:
        """Streamed through the guard, never from a presigned bucket URL."""
        response = _client(portal).get("/api/v1/portal/bills/bill-1/document")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    def test_another_households_invoice_answers_404(self, portal: AsyncMock) -> None:
        """An invoice says what a family pays for their care."""
        portal.bill_document.side_effect = MTCustomerNotFound("no such invoice")

        response = _client(portal).get("/api/v1/portal/bills/bill-9/document")

        assert response.status_code == 404
