from __future__ import annotations

# Standard library imports
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_current_user,
    get_customer_service,
    get_hca_service,
    get_quote_service,
)
from api.exception_handlers import ExceptionHandlers
from api.v1.me.me import router as me_router
from models.auth.user import User
from models.enums import ContractType, QuoteStatus, UserRole
from models.people.customer import Customer
from models.people.hca import Hca
from models.quoting.quote import Quote
from service.customers.exceptions import MTCustomerNotFound
from service.quotes.exceptions import MTQuoteForbidden

ADDRESS = {
    "street": "12 rue de Rivoli",
    "postal_code": "75004",
    "city": "Paris",
    "latitude": 48.8566,
    "longitude": 2.3522,
}


def _user(
    role: UserRole = UserRole.HCA,
    hca_id: Optional[str] = "hca-1",
    user_id: str = "user-1",
) -> User:
    """Build an account.

    Args:
        role (UserRole): The role to grant.
        hca_id (Optional[str]): The assistant record it is bound to.
        user_id (str): The account identifier.

    Returns:
        User: The account.
    """
    return User(
        id=user_id,
        email=f"{user_id}@example.com",
        full_name="Luc Martin",
        hashed_password="$2b$12$abcdefghijklmnopqrstuv",
        role=role,
        hca_id=hca_id,
    )


def _hca() -> Hca:
    """Build an assistant record.

    Returns:
        Hca: The assistant.
    """
    return Hca(
        id="hca-1",
        first_name="Luc",
        last_name="Martin",
        phone_number="+33698765432",
        email="luc.martin@example.com",
        address=ADDRESS,
        contract_type=ContractType.CDI,
    )


def _customer() -> Customer:
    """Build a customer.

    Returns:
        Customer: The customer.
    """
    return Customer(
        id="customer-1",
        first_name="Marie",
        last_name="Durand",
        phone_number="+33612345678",
        email="marie.durand@example.com",
        address=ADDRESS,
    )


def _quote(status: QuoteStatus = QuoteStatus.DRAFT) -> Quote:
    """Build a quote.

    Args:
        status (QuoteStatus): Where it sits in its lifecycle.

    Returns:
        Quote: The quote.
    """
    return Quote(
        id="quote-1",
        reference="D-0142",
        customer_id="customer-1",
        status=status,
        authored_by="user-1",
    )


def _client(
    caller: User,
    hcas: Optional[MagicMock] = None,
    customers: Optional[MagicMock] = None,
    quotes: Optional[MagicMock] = None,
) -> TestClient:
    """Build a client over the self-service router.

    Args:
        caller (User): The account the request is made as.
        hcas (Optional[MagicMock]): The assistant service double.
        customers (Optional[MagicMock]): The customer service double.
        quotes (Optional[MagicMock]): The quote service double.

    Returns:
        TestClient: A client with the guards and services overridden.
    """
    app = FastAPI()
    app.include_router(me_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[get_hca_service] = lambda: hcas or MagicMock()
    app.dependency_overrides[get_customer_service] = lambda: customers or MagicMock()
    app.dependency_overrides[get_quote_service] = lambda: quotes or MagicMock()
    return TestClient(app)


class TestSelfServiceRequiresAnAssistantRecord:
    """Tests for the account-to-assistant binding these routes rest on."""

    @pytest.mark.parametrize("path", ["/api/v1/me/hca", "/api/v1/me/customers"])
    def test_an_unbound_account_is_refused(self, path: str) -> None:
        """A manager's account has no assistant record to serve.

        Args:
            path (str): The self-service route being called.

        Notes:
            Refused with a 403 rather than served an empty list. "You have no
            customers" and "this is not your screen" are different facts, and
            only one of them is true.
        """
        response = _client(_user(UserRole.MANAGER, hca_id=None)).get(path)

        assert response.status_code == 403

    def test_my_quotes_does_not_need_an_assistant_record(self) -> None:
        """Authorship is an account property, not an assistant one.

        Notes:
            The two halves of ``/me`` are scoped differently on purpose. A
            profile and a customer portfolio belong to an *assistant*, so they
            need the record. A quote is authored by an *account*, and a manager
            who writes one has as much claim to "my quotes" as an assistant
            does. Forcing the assistant record here for the sake of symmetry
            would refuse a manager their own work.
        """
        quotes = MagicMock()
        quotes.list = AsyncMock(return_value=[])

        response = _client(
            _user(UserRole.MANAGER, hca_id=None, user_id="user-m"), quotes=quotes
        ).get("/api/v1/me/quotes")

        assert response.status_code == 200
        assert quotes.list.await_args.kwargs["authored_by"] == "user-m"


class TestMyProfile:
    """Tests for an assistant reading and editing their own record."""

    def test_an_assistant_reads_their_own_record(self) -> None:
        """The ordinary case returns the caller's own assistant record."""
        hcas = MagicMock()
        hcas.get = AsyncMock(return_value=_hca())

        response = _client(_user(), hcas=hcas).get("/api/v1/me/hca")

        assert response.status_code == 200
        assert response.json()["id"] == "hca-1"
        hcas.get.assert_awaited_once_with("hca-1")

    def test_the_record_read_is_always_the_callers_own(self) -> None:
        """The identifier comes from the credential, never from the request.

        Notes:
            There is no path parameter to tamper with — this is the structural
            reason an assistant cannot read a colleague's record here.
        """
        hcas = MagicMock()
        hcas.get = AsyncMock(return_value=_hca())

        _client(_user(user_id="user-9"), hcas=hcas).get("/api/v1/me/hca")

        hcas.get.assert_awaited_once_with("hca-1")

    def test_certifications_cannot_be_set_through_the_profile(self) -> None:
        """A payload naming certifications does not reach the service.

        Notes:
            **This is the test the whole endpoint exists for.** An assistant who
            could grant themselves a certification could be routed to work they
            are not trained for. The field is absent from the request model, so
            it is dropped before any code sees it.
        """
        hcas = MagicMock()
        hcas.update_profile = AsyncMock(return_value=_hca())

        response = _client(_user(), hcas=hcas).patch(
            "/api/v1/me/hca",
            json={
                "first_name": "Luc",
                "last_name": "Martin",
                "phone_number": "+33698765432",
                "email": "luc.martin@example.com",
                "address": ADDRESS,
                "certifications": [{"name": "Diplome d'Etat"}],
                "contract_type": "cdi",
            },
        )

        assert response.status_code == 200
        passed = hcas.update_profile.await_args.kwargs
        assert "certifications" not in passed
        assert "contract_type" not in passed


class TestMyCustomers:
    """Tests for the assistant's customer portfolio."""

    def test_the_portfolio_is_scoped_to_the_caller(self) -> None:
        """The assistant identifier is taken from the credential."""
        customers = MagicMock()
        customers.list_for_hca = AsyncMock(return_value=[_customer()])

        response = _client(_user(), customers=customers).get("/api/v1/me/customers")

        assert response.status_code == 200
        assert customers.list_for_hca.await_args.kwargs["hca_id"] == "hca-1"

    def test_the_portfolio_is_scoped_by_account_as_well_as_assistant(self) -> None:
        """Both identifiers reach the service, and they are not the same one.

        Notes:
            The portfolio is a union of two differently-keyed sets: planned
            interventions name the assistant, quotes record the account that
            wrote them. Passing the assistant identifier for both matches no
            quote at all, which silently reduces the portfolio to its
            intervention half — an assistant who has written quotes but has no
            visit yet then sees an empty list and can quote for nobody.
        """
        customers = MagicMock()
        customers.list_for_hca = AsyncMock(return_value=[_customer()])

        response = _client(_user(), customers=customers).get("/api/v1/me/customers")

        assert response.status_code == 200
        passed = customers.list_for_hca.await_args.kwargs
        assert passed["hca_id"] == "hca-1"
        assert passed["account_id"] == "user-1"

    def test_reading_one_customer_is_scoped_by_both_identifiers(self) -> None:
        """The detail view scopes exactly as the list does.

        Notes:
            The two have to agree. A portfolio that lists a customer whose own
            page then answers 404 is worse than either behaviour alone.
        """
        customers = MagicMock()
        customers.get_for_hca = AsyncMock(return_value=_customer())

        response = _client(_user(), customers=customers).get(
            "/api/v1/me/customers/customer-1"
        )

        assert response.status_code == 200
        passed = customers.get_for_hca.await_args.kwargs
        assert passed["hca_id"] == "hca-1"
        assert passed["account_id"] == "user-1"

    def test_a_customer_outside_the_portfolio_is_a_404(self) -> None:
        """Guessing an identifier does not reach somebody else's file."""
        customers = MagicMock()
        customers.get_for_hca = AsyncMock(
            side_effect=MTCustomerNotFound("No customer 'customer-9' exists.")
        )

        response = _client(_user(), customers=customers).get(
            "/api/v1/me/customers/customer-9"
        )

        assert response.status_code == 404


class TestMyQuotes:
    """Tests for an assistant's own quotes."""

    def test_the_list_is_scoped_to_the_author(self) -> None:
        """An assistant sees the quotes they wrote, and no others."""
        quotes = MagicMock()
        quotes.list = AsyncMock(return_value=[_quote()])

        response = _client(_user(), quotes=quotes).get("/api/v1/me/quotes")

        assert response.status_code == 200
        assert quotes.list.await_args.kwargs["authored_by"] == "user-1"

    def test_a_created_quote_is_authored_by_the_caller(self) -> None:
        """The author is the credential, not the payload."""
        quotes = MagicMock()
        quotes.create = AsyncMock(return_value=_quote())

        response = _client(_user(), quotes=quotes).post(
            "/api/v1/me/quotes",
            json={
                "reference": "D-0143",
                "customer_id": "customer-1",
                "authored_by": "user-someone-else",
            },
        )

        assert response.status_code == 201
        assert quotes.create.await_args.kwargs["author_id"] == "user-1"

    def test_submitting_passes_the_caller_as_the_author(self) -> None:
        """The service is given the caller so it can check ownership."""
        quotes = MagicMock()
        quotes.submit_for_validation = AsyncMock(
            return_value=_quote(QuoteStatus.PENDING_VALIDATION)
        )

        response = _client(_user(), quotes=quotes).post(
            "/api/v1/me/quotes/quote-1/submit"
        )

        assert response.status_code == 200
        assert response.json()["status"] == "pending-validation"
        assert quotes.submit_for_validation.await_args.kwargs["author_id"] == "user-1"

    def test_submitting_somebody_elses_quote_is_refused(self) -> None:
        """The service's ownership check surfaces as a 403."""
        quotes = MagicMock()
        quotes.submit_for_validation = AsyncMock(
            side_effect=MTQuoteForbidden("You may only submit a quote you wrote.")
        )

        response = _client(_user(), quotes=quotes).post(
            "/api/v1/me/quotes/quote-1/submit"
        )

        assert response.status_code == 403
