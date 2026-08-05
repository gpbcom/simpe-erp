from __future__ import annotations

# Standard library imports
from typing import Optional
from unittest.mock import AsyncMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_current_user,
    get_customer_service,
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
    ContractType,
    QuoteStatus,
    RegistrationStatus,
    UserRole,
)
from models.people.availability_slot import AvailabilitySlot
from models.people.customer import Customer
from models.people.hca import Hca
from models.quoting.quote import Quote
from service.customers.exceptions import MTCustomerHasQuotes, MTCustomerNotFound
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
        id=f"user-{role.value}",
        email=f"{role.value}@example.com",
        full_name="Test Account",
        role=role,
        hca_id=hca_id if hca_id else ("hca-1" if role is UserRole.HCA else None),
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


def _client(customers: AsyncMock, hcas: AsyncMock, caller: User = None) -> TestClient:
    """Build a client for the people routers alone.

    Args:
        customers (AsyncMock): The stubbed customer service.
        hcas (AsyncMock): The stubbed assistant service.
        caller (User): The account the request is authenticated as.

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
    stub.quotes_for.return_value = [
        Quote(
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

    def test_a_customers_quotes_are_listed(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """The quotes issued to a customer are reachable from them."""
        response = _client(customers, hcas).get("/api/v1/customers/customer-1/quotes")

        assert response.status_code == 200
        assert response.json()[0]["reference"] == "Q-2026-0001"

    def test_deleting_a_quoted_customer_is_409(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A customer on an accounting record cannot be removed.

        Notes:
            409 rather than 403: the request is permitted, the state refuses
            it, and the remedy — stop them instead — is in the message.
        """
        customers.delete.side_effect = MTCustomerHasQuotes("they have quotes")

        response = _client(customers, hcas).delete("/api/v1/customers/customer-1")

        assert response.status_code == 409

    def test_deleting_an_unquoted_customer_answers_204(
        self, customers: AsyncMock, hcas: AsyncMock
    ) -> None:
        """A removable customer is removed."""
        response = _client(customers, hcas).delete("/api/v1/customers/customer-1")

        assert response.status_code == 204


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
