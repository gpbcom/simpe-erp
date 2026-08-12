from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Optional
from unittest.mock import AsyncMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_auth_service,
    get_customer_user,
    get_event_publisher,
    get_planning_service,
    get_current_user,
    get_customer_service,
    get_team_service,
    get_hca_service,
    get_manager_user,
)
from api.exception_handlers import ExceptionHandlers
from api.v1.customers.customers import router as customers_router
from api.v1.hcas.availability import router as availability_router
from api.v1.hcas.hcas import router as hcas_router
from models.auth.user import User
from models.enums import (
    AvailabilityKind,
    BillingPeriodicity,
    ContractType,
    PlanningRunStatus,
    QuoteStatus,
    RegistrationStatus,
    UserRole,
)
from models.planning.planning_run import PlanningRun
from models.people.hca.availability_slot import AvailabilitySlot
from models.people.customer import Customer
from models.people.hca import Hca
from models.quoting.quote import Quote
from service.auth.exceptions import MTAuthCustomerAlreadyHasAccount
from service.customers.exceptions import (
    MTCustomerHasQuotes,
    MTCustomerNotFound,
    MTCustomerNotPromotable,
)
from service.hcas.exceptions import MTHcaForbidden, MTHcaNotFound

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

HCA_PAYLOAD = {
    "company_id": "company-1",
    "first_name": "Luc",
    "last_name": "Martin",
    "phone_number": "+33698765432",
    "email": "luc.martin@example.com",
    "contract_type": "cdi",
    "address": {
        "street": "5 avenue de la Gare",
        "postal_code": "75012",
        "city": "Paris",
    },
}


def _user(role: UserRole = UserRole.MANAGER, hca_id: Optional[str] = None) -> User:
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
        customer_id="customer-1" if role is UserRole.CUSTOMER else None,
    )


def _customer() -> Customer:
    """Build a stored customer.

    Returns:
        Customer: The customer.
    """
    return Customer(id="customer-1", **CUSTOMER_PAYLOAD)


def _hca() -> Hca:
    """Build a stored assistant.

    Returns:
        Hca: The assistant.
    """
    return Hca(id="hca-1", **HCA_PAYLOAD)


def _slot() -> AvailabilitySlot:
    """Build a stored absence.

    Returns:
        AvailabilitySlot: The absence.
    """
    return AvailabilitySlot(
        id="slot-1",
        hca_id="hca-1",
        start_date="2026-08-09",
        end_date="2026-08-09",
        kind=AvailabilityKind.DAY_OFF,
    )


def _client(
    customers: AsyncMock,
    hcas: AsyncMock,
    caller: User = None,
    plannings: AsyncMock = None,
    auth: AsyncMock = None,
) -> TestClient:
    """Build a client for the people routers alone.

    Args:
        customers (AsyncMock): The stubbed customer service.
        hcas (AsyncMock): The stubbed assistant service.
        caller (User): The account the request is authenticated as.
        plannings (AsyncMock): The stubbed planning service. Defaults to one
            reporting that nobody has future work, which is the 204 path.
        auth (AsyncMock): The stubbed authentication service, needed only by
            the portal-invitation route.

    Returns:
        TestClient: A client over an app mounting only the routers under test.

    Notes:
        Every service dependency is replaced, so no database connection is
        attempted — an unmocked repository would make these hang on a
        connection attempt rather than fail fast.

        The production handler set is registered, because the routers let their
        domain exceptions escape rather than translating each one.
    """
    caller = caller if caller else _user()
    app = FastAPI()
    app.include_router(customers_router)
    app.include_router(hcas_router)
    app.include_router(availability_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_customer_service] = lambda: customers
    app.dependency_overrides[get_hca_service] = lambda: hcas
    app.dependency_overrides[get_manager_user] = lambda: caller
    app.dependency_overrides[get_current_user] = lambda: caller
    # Both delete routes end in a replan, so they reach the planning service
    # and the broker. Stubbed to "this person had no future visit", which is
    # the 204 path every test here but the replan ones expects.
    if plannings is None:
        plannings = AsyncMock()
        plannings.future_period_for_hca.return_value = None
        plannings.future_period_for_customer.return_value = None
    app.dependency_overrides[get_planning_service] = lambda: plannings
    # The customer book narrows to the households the caller's teams serve, so
    # the route reaches the team service. This double answers as an
    # administrator does — ``None`` means every household — which keeps these
    # fixtures asserting what they were written to assert.
    scoped_teams = AsyncMock()
    scoped_teams.readable_customer_ids.return_value = None
    scoped_teams.readable_hca_ids.return_value = None
    scoped_teams.readable_team_ids.return_value = None
    app.dependency_overrides[get_team_service] = lambda: scoped_teams
    app.dependency_overrides[get_event_publisher] = lambda: AsyncMock()
    if auth is None:
        auth = AsyncMock()
        auth.create_customer_account.return_value = (
            _user(UserRole.CUSTOMER),
            "Temp0rary!Pass",
        )
    app.dependency_overrides[get_auth_service] = lambda: auth
    return TestClient(app)


@pytest.fixture
def customers() -> AsyncMock:
    """Return a stubbed customer service.

    Returns:
        AsyncMock: The service double.
    """
    stub = AsyncMock()
    stub.create.return_value = _customer()
    stub.get.return_value = _customer()
    stub.list.return_value = [_customer()]
    stub.update.return_value = _customer()
    stub.set_status.return_value = _customer()
    stub.set_billing_periodicity.return_value = _customer()
    stub.promote.return_value = _customer()
    stub.quotes_for.return_value = [
        Quote(
            company_id="company-1",
            id="quote-1",
            reference="Q-2026-0001",
            customer_id="customer-1",
            status=QuoteStatus.DRAFT,
        )
    ]
    stub.delete.return_value = None
    return stub


@pytest.fixture
def hcas() -> AsyncMock:
    """Return a stubbed assistant service.

    Returns:
        AsyncMock: The service double.
    """
    stub = AsyncMock()
    stub.create.return_value = _hca()
    stub.get.return_value = _hca()
    stub.list.return_value = [_hca()]
    stub.set_employment.return_value = _hca()
    stub.add_availability.return_value = _slot()
    stub.list_availability.return_value = [_slot()]
    stub.remove_availability.return_value = None
    stub.delete.return_value = None
    return stub


class TestCustomerEndpoints:
    """Tests for the customer routes."""

    def test_creating_a_customer_answers_201(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """The ordinary case works."""
        response = _client(customers, hcas).post(
            "/api/v1/customers", json=CUSTOMER_PAYLOAD
        )

        assert response.status_code == 201
        assert response.json()["id"] == "customer-1"

    def test_listing_customers_answers_200(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A page of customers comes back."""
        response = _client(customers, hcas).get("/api/v1/customers")

        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_an_absent_customer_is_404(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """The service's refusal surfaces as not-found."""
        customers.get.side_effect = MTCustomerNotFound("no such customer")

        response = _client(customers, hcas).get("/api/v1/customers/ghost")

        assert response.status_code == 404

    def test_the_path_identifier_is_what_is_updated(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A payload naming another customer edits the addressed one."""
        _client(customers, hcas).put(
            "/api/v1/customers/customer-1",
            json={**CUSTOMER_PAYLOAD, "id": "customer-99"},
        )

        assert customers.update.await_args.args[0] == "customer-1"

    def test_stopping_a_customer_takes_only_a_status(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """The single-field payload is what reaches the service."""
        response = _client(customers, hcas).patch(
            "/api/v1/customers/customer-1/status",
            json={"registration_status": "stopped"},
        )

        assert response.status_code == 200
        assert customers.set_status.await_args.args[1] is RegistrationStatus.STOPPED

    def test_an_unknown_status_is_422(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A status outside the enumeration is refused before the service."""
        response = _client(customers, hcas).patch(
            "/api/v1/customers/customer-1/status",
            json={"registration_status": "suspended"},
        )

        assert response.status_code == 422
        customers.set_status.assert_not_awaited()

    def test_a_customer_is_given_their_own_billing_granularity(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """The periodicity reaches the service, with who asked for it."""
        response = _client(customers, hcas).patch(
            "/api/v1/customers/customer-1/billing-periodicity",
            json={"periodicity": "weekly"},
        )

        assert response.status_code == 200
        assert (
            customers.set_billing_periodicity.await_args.args[1]
            is BillingPeriodicity.WEEKLY
        )

    def test_a_null_periodicity_puts_them_back_on_the_agency_rule(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """**Null is a value on this route, not an omission.**

        Notes:
            It is how a manager takes an override off. Read as "no change", an
            override could be set and never removed from any screen.
        """
        response = _client(customers, hcas).patch(
            "/api/v1/customers/customer-1/billing-periodicity",
            json={"periodicity": None},
        )

        assert response.status_code == 200
        assert customers.set_billing_periodicity.await_args.args[1] is None

    def test_an_unknown_periodicity_is_422(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A granularity nothing can bill on is refused before the service."""
        response = _client(customers, hcas).patch(
            "/api/v1/customers/customer-1/billing-periodicity",
            json={"periodicity": "fortnightly"},
        )

        assert response.status_code == 422
        customers.set_billing_periodicity.assert_not_awaited()

    def test_setting_the_granularity_of_an_unknown_customer_is_404(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A customer who is gone is a 404, not a silent success."""
        customers.set_billing_periodicity.side_effect = MTCustomerNotFound("gone")

        response = _client(customers, hcas).patch(
            "/api/v1/customers/ghost/billing-periodicity",
            json={"periodicity": "yearly"},
        )

        assert response.status_code == 404

    def test_a_customers_quotes_are_listed(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """The quotes issued to a customer are reachable from them."""
        response = _client(customers, hcas).get("/api/v1/customers/customer-1/quotes")

        assert response.status_code == 200
        assert response.json()[0]["reference"] == "Q-2026-0001"

    def test_a_customer_whose_quote_cannot_be_identified_is_409(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """An unidentifiable quote stops the whole deletion.

        Notes:
            409 rather than 403: the request is permitted and the state
            refuses it. Deleting the customer anyway would leave the quote
            behind, which is the orphan the cascade exists to avoid.
        """
        customers.delete.side_effect = MTCustomerHasQuotes("an unidentified quote")

        response = _client(customers, hcas).delete("/api/v1/customers/customer-1")

        assert response.status_code == 409

    def test_deleting_a_customer_with_no_future_visit_answers_204(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """Nothing to replan means nothing is queued.

        Notes:
            Queueing a run that would place the same visits in the same slots
            costs thirty seconds of a worker and makes the calendar flicker for
            no reason.
        """
        response = _client(customers, hcas).delete("/api/v1/customers/customer-1")

        assert response.status_code == 204
        assert response.content == b""

    def test_deleting_a_customer_with_future_visits_answers_202(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A replan is queued over exactly the days they were visited on.

        Notes:
            The span is measured **before** the delete: their visits go with
            their quotes, so asking afterwards would find nothing and replan
            nothing.
        """
        plannings = AsyncMock()
        plannings.future_period_for_customer.return_value = (
            date(2026, 8, 10),
            date(2026, 8, 14),
        )
        plannings.queue_replan.return_value = PlanningRun(
            company_id="company-1",
            id="run-1",
            status=PlanningRunStatus.PENDING,
            requested_by="user-1",
            period_start=date(2026, 8, 10),
            period_end=date(2026, 8, 14),
        )

        response = _client(customers, hcas, plannings=plannings).delete(
            "/api/v1/customers/customer-1"
        )

        assert response.status_code == 202
        assert response.json()["id"] == "run-1"
        assert plannings.queue_replan.await_args.kwargs["period"] == (
            date(2026, 8, 10),
            date(2026, 8, 14),
        )


class TestCustomerFiltering:
    """Tests for what the customers screen sends in the query string.

    Notes:
        The filters are a Pydantic model bound with ``Depends()``, which is what
        flattens them into individual query parameters. Bound the other
        documented way they would arrive as one parameter taking a JSON object
        and every request here would answer 422 — so these tests are as much
        about the binding as about the filters.
    """

    def test_the_status_filter_reaches_the_service(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """``?status=prospect`` arrives as the enum member."""
        response = _client(customers, hcas).get("/api/v1/customers?status=prospect")

        assert response.status_code == 200
        applied = customers.list.await_args.kwargs["customer_filter"]
        assert applied.status is RegistrationStatus.PROSPECT

    def test_every_filter_survives_the_query_string(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """All eight arrive together and none of them is dropped.

        Args:
            customers (AsyncMock): The stubbed customer service.
            hcas (AsyncMock): The stubbed assistant service.

        Notes:
            Sent as one request rather than eight, because what has actually
            broken here is the *binding* — a model bound the wrong way fails for
            all of them at once, and a per-filter test would say so eight times.
        """
        response = _client(customers, hcas).get(
            "/api/v1/customers?search=Durand&status=active&city=Paris"
            "&postal_code=75004&email=example.com&phone=0612"
            "&has_ongoing_arrangement=true&is_geocoded=false"
        )

        assert response.status_code == 200
        assert customers.list.await_args.kwargs["customer_filter"].model_dump() == {
            "search": "Durand",
            "status": RegistrationStatus.ACTIVE,
            "city": "Paris",
            "postal_code": "75004",
            "email": "example.com",
            "phone": "0612",
            "has_ongoing_arrangement": True,
            "is_geocoded": False,
        }

    def test_a_false_flag_is_a_filter_rather_than_an_absence(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """**``?is_geocoded=false`` must not read as "no filter".**

        Args:
            customers (AsyncMock): The stubbed customer service.
            hcas (AsyncMock): The stubbed assistant service.

        Notes:
            "Whose address failed to resolve" is the question this filter exists
            to answer — those are the customers nothing can ever be planned for.
            Read as an absence it would return the whole book instead, which
            looks like a filter that does not work rather than a wrong one.
        """
        _client(customers, hcas).get("/api/v1/customers?is_geocoded=false")

        assert customers.list.await_args.kwargs["customer_filter"].is_geocoded is False

    def test_an_unfiltered_list_narrows_nothing(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """Opening the screen shows the whole book."""
        _client(customers, hcas).get("/api/v1/customers")

        assert customers.list.await_args.kwargs["customer_filter"].is_empty()

    def test_an_unknown_status_answers_422(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A status the system has no word for is refused, not ignored.

        Args:
            customers (AsyncMock): The stubbed customer service.
            hcas (AsyncMock): The stubbed assistant service.

        Notes:
            422 rather than an empty page: an empty page is what a valid filter
            matching nobody looks like, and the two must not be confusable.
        """
        response = _client(customers, hcas).get("/api/v1/customers?status=lapsed")

        assert response.status_code == 422
        customers.list.assert_not_awaited()


class TestCustomerPromotion:
    """Tests for the route that puts a customer into the planning."""

    def test_promoting_a_prospect_answers_200(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """The ordinary case works, and needs no payload."""
        response = _client(customers, hcas).post("/api/v1/customers/customer-1/promote")

        assert response.status_code == 200
        customers.promote.assert_awaited_once_with("customer-1")

    def test_promoting_somebody_who_is_not_a_prospect_answers_409(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A refused transition is a conflict, not a bad request.

        Args:
            customers (AsyncMock): The stubbed customer service.
            hcas (AsyncMock): The stubbed assistant service.

        Notes:
            The request is well formed and the caller is allowed to make it;
            what refuses is the customer's current state. 400 would send the
            screen looking for a mistake in what it sent.
        """
        customers.promote.side_effect = MTCustomerNotPromotable("already active")

        response = _client(customers, hcas).post("/api/v1/customers/customer-1/promote")

        assert response.status_code == 409

    def test_promoting_an_absent_customer_answers_404(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A typo in the identifier is reported as such."""
        customers.promote.side_effect = MTCustomerNotFound("no such customer")

        response = _client(customers, hcas).post("/api/v1/customers/ghost/promote")

        assert response.status_code == 404

    def test_the_promote_route_is_mounted(self) -> None:
        """A route written but never included would pass every test above.

        Notes:
            The tests above mount the router by hand; this reads the real
            application, where a missing ``include_router`` is the one failure
            a hand-built app cannot see.
        """
        from api.main import app

        assert "/api/v1/customers/{customer_id}/promote" in app.openapi()["paths"]

    def test_only_a_manager_may_promote(self) -> None:
        """**The guard is asserted on the route, not on an override.**

        Notes:
            Every test above overrides ``get_manager_user``, which is what lets
            them run without an authentication stack — and which means none of
            them would notice the guard being dropped. This reads the dependency
            graph of the very router object the application includes. Manager
            access is manager *and* administrator: the roles are ranked and an
            administrator outranks a manager.

            Read from the router rather than from ``app.routes``, because this
            FastAPI represents an included router as one opaque entry and the
            leaf routes are not reachable from the application object.
        """
        matching = [
            route
            for route in customers_router.routes
            if getattr(route, "path", None) == "/api/v1/customers/{customer_id}/promote"
        ]
        assert matching, "The promote route is not on the router."

        guards = {
            dependency.call
            for dependency in matching[0].dependant.dependencies
            if dependency.call is not None
        }
        assert get_manager_user in guards


class TestCustomerPortalAccounts:
    """Tests for the route that gives a household access to their space."""

    def test_inviting_a_customer_answers_201(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """The ordinary case returns the one-time password."""
        response = _client(customers, hcas).post(
            "/api/v1/customers/customer-1/account",
            json={"email": "marie@example.com", "full_name": "Marie Durand"},
        )

        assert response.status_code == 201
        assert response.json()["temporary_password"] == "Temp0rary!Pass"
        assert response.json()["must_change_password"] is False

    def test_the_household_comes_from_the_path(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """**Not from the body, which carries no identifier at all.**

        Notes:
            The customer is resolved before anything is created, so a typo is a
            404 rather than an invitation onto a file that does not exist. The
            payload having no place to name a household is what removes the
            second answer entirely.
        """
        _client(customers, hcas).post(
            "/api/v1/customers/customer-1/account",
            json={
                "email": "marie@example.com",
                "full_name": "Marie Durand",
                "customer_id": "customer-99",
            },
        )

        customers.get.assert_awaited_once_with("customer-1")

    def test_the_agency_comes_from_the_caller(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """The household carries none, so the manager's agency is used."""
        auth = AsyncMock()
        auth.create_customer_account.return_value = (
            _user(UserRole.CUSTOMER),
            "Temp0rary!Pass",
        )

        _client(customers, hcas, auth=auth).post(
            "/api/v1/customers/customer-1/account",
            json={"email": "marie@example.com", "full_name": "Marie Durand"},
        )

        assert auth.create_customer_account.await_args.kwargs["company_id"] == (
            "company-1"
        )

    def test_inviting_an_absent_customer_answers_404(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A typo in the identifier is reported before anything is created."""
        customers.get.side_effect = MTCustomerNotFound("no such customer")

        response = _client(customers, hcas).post(
            "/api/v1/customers/ghost/account",
            json={"email": "marie@example.com", "full_name": "Marie Durand"},
        )

        assert response.status_code == 404

    def test_a_second_invitation_answers_409(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """One account per household, refused rather than duplicated."""
        auth = AsyncMock()
        auth.create_customer_account.side_effect = MTAuthCustomerAlreadyHasAccount(
            "already has access"
        )

        response = _client(customers, hcas, auth=auth).post(
            "/api/v1/customers/customer-1/account",
            json={"email": "marie@example.com", "full_name": "Marie Durand"},
        )

        assert response.status_code == 409

    def test_a_payload_with_no_name_answers_422(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """An account with no display name has nothing to greet anybody by."""
        response = _client(customers, hcas).post(
            "/api/v1/customers/customer-1/account",
            json={"email": "marie@example.com", "full_name": "  "},
        )

        assert response.status_code == 422

    def test_only_a_manager_may_invite(self) -> None:
        """The guard is asserted on the router's own dependency graph."""
        matching = [
            route
            for route in customers_router.routes
            if getattr(route, "path", None) == "/api/v1/customers/{customer_id}/account"
        ]
        assert matching, "The invitation route is not on the router."

        guards = {
            dependency.call
            for dependency in matching[0].dependant.dependencies
            if dependency.call is not None
        }
        assert get_manager_user in guards
        # And emphatically not the customer guard: a household must not be able
        # to mint access for another household.
        assert get_customer_user not in guards


class TestHcaEndpoints:
    """Tests for the assistant routes."""

    def test_creating_an_assistant_answers_201(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """The ordinary case works."""
        response = _client(customers, hcas).post("/api/v1/hcas", json=HCA_PAYLOAD)

        assert response.status_code == 201
        assert response.json()["id"] == "hca-1"

    def test_an_absent_assistant_is_404(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """The service's refusal surfaces as not-found."""
        hcas.get.side_effect = MTHcaNotFound("no such assistant")

        response = _client(customers, hcas).get("/api/v1/hcas/ghost")

        assert response.status_code == 404

    def test_employment_is_changed_through_its_own_route(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """Contract and certifications reach the service."""
        response = _client(customers, hcas).patch(
            "/api/v1/hcas/hca-1/employment",
            json={"contract_type": "cdd", "certifications": [{"name": "SST"}]},
        )

        assert response.status_code == 200
        assert hcas.set_employment.await_args.args[1] is ContractType.CDD

    def test_there_is_no_manager_route_accepting_a_whole_assistant(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A manager cannot rewrite an assistant's address or contact details.

        Notes:
            **This is the enforcement of "a manager may modify only the
            contract type and the certifications".** It is a property of the
            route table, not a check inside a handler: there is no PUT or PATCH
            on ``/hcas/{id}`` at all, so the fuller payload has nowhere to go.
            A route added later that accepts one would fail this test.
        """
        client = _client(customers, hcas)

        assert client.put("/api/v1/hcas/hca-1", json=HCA_PAYLOAD).status_code == 405
        assert client.patch("/api/v1/hcas/hca-1", json=HCA_PAYLOAD).status_code == 405

    def test_an_unknown_contract_type_is_422(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A contract outside the enumeration is refused before the service."""
        response = _client(customers, hcas).patch(
            "/api/v1/hcas/hca-1/employment", json={"contract_type": "permanent"}
        )

        assert response.status_code == 422
        hcas.set_employment.assert_not_awaited()


class TestAvailabilityEndpoints:
    """Tests for declaring availability."""

    def test_an_assistant_files_their_own_absence(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """This is the route by which an assistant declares availability."""
        response = _client(customers, hcas, _user(UserRole.HCA)).post(
            "/api/v1/hcas/hca-1/availability",
            json={
                "hca_id": "hca-1",
                "start_date": "2026-08-09",
                "end_date": "2026-08-09",
                "kind": "day-off",
            },
        )

        assert response.status_code == 201

    def test_filing_against_a_colleague_is_403(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """The service's refusal surfaces as forbidden.

        Notes:
            The decision is the service's — the route cannot make it — and this
            pins that what reaches the caller is a 403 rather than a 500.
        """
        hcas.add_availability.side_effect = MTHcaForbidden("not yours")

        response = _client(customers, hcas, _user(UserRole.HCA)).post(
            "/api/v1/hcas/hca-2/availability",
            json={
                "hca_id": "hca-2",
                "start_date": "2026-08-09",
                "end_date": "2026-08-09",
                "kind": "day-off",
            },
        )

        assert response.status_code == 403

    def test_the_caller_is_passed_to_the_service(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """Without the caller the ownership check has nothing to compare."""
        caller = _user(UserRole.HCA)
        _client(customers, hcas, caller).get("/api/v1/hcas/hca-1/availability")

        assert hcas.list_availability.await_args.args[1] is caller

    def test_the_owning_assistant_comes_from_the_path(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A body naming a colleague files against the addressed assistant.

        Notes:
            Two defences, not one: the path wins over the payload here, and the
            service refuses if the path is not the caller's own.
        """
        _client(customers, hcas, _user(UserRole.HCA)).post(
            "/api/v1/hcas/hca-1/availability",
            json={
                "hca_id": "hca-2",
                "start_date": "2026-08-09",
                "end_date": "2026-08-09",
                "kind": "day-off",
            },
        )

        assert hcas.add_availability.await_args.args[0] == "hca-1"

    def test_withdrawing_an_absence_answers_204(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A withdrawal returns nothing."""
        response = _client(customers, hcas, _user(UserRole.HCA)).delete(
            "/api/v1/hcas/hca-1/availability/slot-1"
        )

        assert response.status_code == 204


class TestProductionRegistration:
    """Tests that the real application actually mounts these routes."""

    def test_the_people_routes_are_mounted(self) -> None:
        """A router written but never included would pass every test above."""
        from api.main import app

        paths = set(app.openapi()["paths"])

        assert "/api/v1/customers" in paths
        assert "/api/v1/customers/{customer_id}/status" in paths
        assert "/api/v1/hcas" in paths
        assert "/api/v1/hcas/{hca_id}/employment" in paths
        assert "/api/v1/hcas/{hca_id}/availability" in paths

    def test_no_route_accepts_a_whole_assistant_from_a_manager(self) -> None:
        """The permission holds in the real route table, not just in a test app.

        Notes:
            The check above uses a hand-built app mounting two routers. This
            one reads production, where a third router could have added the
            very route the rule forbids.
        """
        from api.main import app

        methods = app.openapi()["paths"].get("/api/v1/hcas/{hca_id}", {})

        assert set(methods) <= {"get", "delete"}
