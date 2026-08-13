from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_admin_user,
    get_auth_service,
    get_company_service,
    get_current_user,
    get_customer_service,
    get_team_service,
    get_hca_service,
    get_quote_service,
)
from api.exception_handlers import ExceptionHandlers
from api.v1.me.me import router as me_router
from models.auth.user import User
from models.organisation.companies.company import Company
from models.enums import Language, ContractType, QuoteStatus, UserRole
from models.people.customer import Customer
from models.people.hca import Hca
from models.quoting.quote import Quote
from service.auth.exceptions import MTAuthEmailAlreadyRegistered
from service.customers.exceptions import MTCustomerNotFound
from service.quotes.exceptions import MTQuoteForbidden
from storage.s3.exceptions import MTS3PayloadTooLarge, MTS3UnsupportedContentType
from tests.annotations import ModelInput

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
        company_id="company-1",
        id=user_id,
        email=f"{user_id}@example.com",
        full_name="Luc Martin",
        hashed_password="$2b$12$abcdefghijklmnopqrstuv",
        role=role,
        hca_id=hca_id,
    )


def _company() -> Company:
    """Build an agency.

    Returns:
        Company: The agency.
    """
    return Company(
        id="company-1",
        name="Aide Domicile Paris",
        registration_number="12345678900011",
        contact_email="contact@simple-erp.fr",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _hca() -> Hca:
    """Build an assistant record.

    Returns:
        Hca: The assistant.
    """
    return Hca(
        company_id="company-1",
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
        company_id="company-1",
        team_id="team-1",
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
    auth: Optional[MagicMock] = None,
    companies: Optional[MagicMock] = None,
) -> TestClient:
    """Build a client over the self-service router.

    Args:
        caller (User): The account the request is made as.
        hcas (Optional[MagicMock]): The assistant service double.
        customers (Optional[MagicMock]): The customer service double.
        quotes (Optional[MagicMock]): The quote service double.
        auth (Optional[MagicMock]): The authentication service double.
        companies (Optional[MagicMock]): The company service double.

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
    # The customer book narrows to the households the caller's teams serve, so
    # the route reaches the team service. This double answers as an
    # administrator does — ``None`` means every household — which keeps these
    # fixtures asserting what they were written to assert.
    scoped_teams = AsyncMock()
    scoped_teams.readable_customer_ids.return_value = None
    scoped_teams.readable_hca_ids.return_value = None
    scoped_teams.readable_team_ids.return_value = None
    app.dependency_overrides[get_team_service] = lambda: scoped_teams
    app.dependency_overrides[get_auth_service] = lambda: auth or MagicMock()
    app.dependency_overrides[get_company_service] = lambda: companies or MagicMock()
    # The admin guard is a separate dependency from `get_current_user`, so the
    # company routes need it overridden too — otherwise they resolve the real
    # one, which reads a request state this client never sets.
    app.dependency_overrides[get_admin_user] = lambda: caller
    return TestClient(app)


class TestQuoteLineCategoryIsRequired:
    """Tests that a quote line cannot be written without a VAT category."""

    def _payload(self, **overrides: ModelInput) -> dict:
        """Return a quote payload with one line.

        Args:
            **overrides: Fields to change on the line.

        Returns:
            dict: The request body.
        """
        line = {
            "name": "Aide a la toilette",
            "intervention_type_id": "type-1",
            "service_category": "necessity",
            "service_date": "2026-09-01",
            "earliest_start": "09:00:00",
            "latest_end": "12:00:00",
            "duration_minutes": 60,
        }
        line.update(overrides)
        return {"reference": "QA-1", "customer_id": "cu-1", "lines": [line]}

    def test_a_line_with_a_category_is_accepted(self) -> None:
        """The ordinary case."""
        quotes = MagicMock()
        quotes.create = AsyncMock(
            side_effect=lambda payload, company_id, author_id: payload.to_quote(
                company_id, "team-1"
            )
        )

        response = _client(_user(), quotes=quotes).post(
            "/api/v1/me/quotes", json=self._payload()
        )

        assert response.status_code == 201

    def test_a_line_without_a_category_is_refused(self) -> None:
        """**No default, because both defaults are wrong.**

        Notes:
            Necessity would understate the tax on every line somebody forgot
            to set — an error that surfaces at the tax return rather than on
            the screen. Comfort would overcharge families entitled to the
            reduced rate. So the request is refused rather than guessed at.
        """
        quotes = MagicMock()
        quotes.create = AsyncMock()
        body = self._payload()
        del body["lines"][0]["service_category"]

        response = _client(_user(), quotes=quotes).post("/api/v1/me/quotes", json=body)

        assert response.status_code == 422
        quotes.create.assert_not_awaited()

    @pytest.mark.parametrize("value", ["", "luxury", None, 5])
    def test_an_unknown_category_is_refused(self, value: ModelInput) -> None:
        """A category the tax code does not have a rate for.

        Args:
            value (ModelInput): The rejected category.
        """
        quotes = MagicMock()
        quotes.create = AsyncMock()

        response = _client(_user(), quotes=quotes).post(
            "/api/v1/me/quotes", json=self._payload(service_category=value)
        )

        assert response.status_code == 422
        quotes.create.assert_not_awaited()

    def test_the_category_reaches_the_service_unchanged(self) -> None:
        """What the screen chose is what gets priced."""
        quotes = MagicMock()
        quotes.create = AsyncMock(
            side_effect=lambda payload, company_id, author_id: payload.to_quote(
                company_id, "team-1"
            )
        )

        _client(_user(), quotes=quotes).post(
            "/api/v1/me/quotes", json=self._payload(service_category="comfort")
        )

        written = quotes.create.await_args.args[0]
        assert written.lines[0].service_category.value == "comfort"


class TestMyCompany:
    """Tests for an administrator reading and editing their own agency."""

    def test_the_agency_read_is_the_one_on_the_credential(self) -> None:
        """**There is no identifier to pass, and that is the point.**

        Notes:
            An administrator signing in has no way to know their agency's
            identifier, and a browser holding one it read from somewhere else
            is how a screen ends up editing the wrong tenant. The route takes
            the value from the credential instead.
        """
        companies = MagicMock()
        companies.get = AsyncMock(return_value=_company())

        response = _client(_user(UserRole.ADMIN), companies=companies).get(
            "/api/v1/me/company"
        )

        assert response.status_code == 200
        companies.get.assert_awaited_once_with("company-1")

    def test_the_details_can_be_changed(self) -> None:
        """The ordinary case."""
        companies = MagicMock()
        companies.get = AsyncMock(return_value=_company())
        companies.update = AsyncMock(
            return_value=_company().model_copy(update={"name": "Aide Domicile Nord"})
        )

        response = _client(_user(UserRole.ADMIN), companies=companies).put(
            "/api/v1/me/company",
            json={"name": "Aide Domicile Nord", "is_accepting_applications": False},
        )

        assert response.status_code == 200
        assert companies.update.await_args.args[0] == "company-1"

    def test_the_stored_identifier_and_timestamps_survive_a_write(self) -> None:
        """**The failure the read-before-write exists to prevent.**

        Notes:
            The payload carries no identifier and no timestamps. Building a
            fresh ``Company`` from it would blank whatever it does not mention,
            so the existing agency is read first and copied over.
        """
        existing = _company()
        companies = MagicMock()
        companies.get = AsyncMock(return_value=existing)
        companies.update = AsyncMock(side_effect=lambda _id, company: company)

        _client(_user(UserRole.ADMIN), companies=companies).put(
            "/api/v1/me/company", json={"name": "Renamed"}
        )

        written = companies.update.await_args.args[1]
        assert written.id == existing.id
        assert written.created_at == existing.created_at

    @pytest.mark.parametrize("method", ["GET", "PUT"])
    def test_both_company_routes_are_administrator_gated(self, method: str) -> None:
        """**A manager runs the agency's work, not its legal identity.**

        Args:
            method (str): The verb under test.

        Notes:
            Asserted against the route's declared dependencies rather than by
            calling it as a manager. ``get_admin_user`` reads the account from
            request state, which the middleware sets and a bare test client
            does not — so calling it would answer 500 and the test would pass
            for a reason that has nothing to do with the role.

            Reading the dependency graph is also the stronger assertion: it
            fails if somebody swaps the guard for the manager one, which a
            status-code check on an unauthenticated client would not.
        """
        matching = [
            route
            for route in me_router.routes
            if getattr(route, "path", None) == "/api/v1/me/company"
            and method in getattr(route, "methods", set())
        ]
        assert matching, f"No {method} /api/v1/me/company route is registered."

        guards = {
            dependency.call
            for dependency in matching[0].dependant.dependencies
            if dependency.call is not None
        }
        assert get_admin_user in guards
        assert get_current_user not in guards

    @pytest.mark.parametrize(
        "field,value", [("id", "company-9"), ("created_at", "2020-01-01T00:00:00Z")]
    )
    def test_a_field_the_payload_does_not_own_is_ignored(
        self, field: str, value: str
    ) -> None:
        """A payload naming another agency does not reach the service.

        Args:
            field (str): The smuggled field.
            value (str): What it would be set to.
        """
        existing = _company()
        companies = MagicMock()
        companies.get = AsyncMock(return_value=existing)
        companies.update = AsyncMock(side_effect=lambda _id, company: company)

        _client(_user(UserRole.ADMIN), companies=companies).put(
            "/api/v1/me/company", json={"name": "Renamed", field: value}
        )

        assert companies.update.await_args.args[0] == "company-1"
        assert companies.update.await_args.args[1].id == existing.id

    def test_a_blank_name_is_refused(self) -> None:
        """The one field nothing else can work around."""
        companies = MagicMock()
        companies.get = AsyncMock(return_value=_company())
        companies.update = AsyncMock()

        response = _client(_user(UserRole.ADMIN), companies=companies).put(
            "/api/v1/me/company", json={"name": "   "}
        )

        assert response.status_code == 422
        companies.update.assert_not_awaited()


class TestMyAccount:
    """Tests for the routes every signed-in account can reach."""

    @pytest.mark.parametrize(
        "role,hca_id",
        [
            (UserRole.HCA, "hca-1"),
            (UserRole.MANAGER, None),
            (UserRole.ADMIN, None),
        ],
    )
    def test_every_role_can_read_its_own_account(
        self, role: UserRole, hca_id: Optional[str]
    ) -> None:
        """**The regression this route exists for.**

        Args:
            role (UserRole): The role signing in.
            hca_id (Optional[str]): The assistant record it is bound to.

        Notes:
            The account screen was built on ``GET /me/hca``, which refuses any
            account with no assistant record — every manager and every
            administrator. They were shown an error page in place of their own
            details, and nothing on it said why. This asserts all three roles
            get an answer, so the screen has something to render for each.
        """
        response = _client(_user(role, hca_id=hca_id)).get("/api/v1/me/account")

        assert response.status_code == 200
        assert response.json()["role"] == role.value

    def test_the_account_read_is_the_credentials_own(self) -> None:
        """There is no identifier to point at somebody else's account."""
        response = _client(_user(user_id="user-9")).get("/api/v1/me/account")

        assert response.json()["email"] == "user-9@example.com"

    def test_the_password_hash_is_never_returned(self) -> None:
        """The account carries one; the response must not.

        Notes:
            Worth asserting rather than assuming. ``UserResponse`` drops it,
            but this route is the one a browser calls on every visit to the
            account screen, so a hash leaking here would leak on every page
            load of every account.
        """
        body = _client(_user()).get("/api/v1/me/account").json()

        assert "hashed_password" not in body

    def test_the_details_can_be_changed(self) -> None:
        """The ordinary case: a new display name and address are stored."""
        auth = MagicMock()
        auth.update_account = AsyncMock(
            return_value=_user().model_copy(
                update={
                    "first_name": "Luc",
                    "last_name": "Martin-Durand",
                    "email": "luc@simple-erp.fr",
                }
            )
        )

        response = _client(_user(), auth=auth).patch(
            "/api/v1/me/account",
            json={"full_name": "Luc Martin-Durand", "email": "luc@simple-erp.fr"},
        )

        assert response.status_code == 200
        assert response.json()["full_name"] == "Luc Martin-Durand"
        assert auth.update_account.await_args.kwargs == {
            "full_name": "Luc Martin-Durand",
            "email": "luc@simple-erp.fr",
            "language": Language.FR,
        }

    def test_the_account_changed_is_the_callers_own(self) -> None:
        """The account comes from the credential, not from the payload.

        Notes:
            The service takes the ``User`` itself rather than an identifier, so
            there is nothing in the request that could name a different one.
            This asserts the route passes the caller through unchanged.
        """
        caller = _user(user_id="user-7")
        auth = MagicMock()
        auth.update_account = AsyncMock(return_value=caller)

        _client(caller, auth=auth).patch(
            "/api/v1/me/account",
            json={"full_name": "Luc", "email": "luc@simple-erp.fr"},
        )

        assert auth.update_account.await_args.args[0] is caller

    @pytest.mark.parametrize("field", ["role", "is_active", "hca_id", "company_id"])
    def test_a_privileged_field_in_the_payload_is_ignored(self, field: str) -> None:
        """**The check the whole shape of the payload rests on.**

        Args:
            field (str): The field somebody might smuggle in.

        Notes:
            ``AccountUpdateRequest`` has no such field, so a payload carrying
            one is parsed without it rather than refused — and the service is
            called with the display name and address alone. An account screen
            is exactly where somebody would try to grant themselves a role, and
            this asserts the attempt reaches nothing.
        """
        auth = MagicMock()
        auth.update_account = AsyncMock(return_value=_user())

        response = _client(_user(), auth=auth).patch(
            "/api/v1/me/account",
            json={
                "full_name": "Luc",
                "email": "luc@simple-erp.fr",
                field: "admin" if field == "role" else "smuggled",
            },
        )

        assert response.status_code == 200
        assert set(auth.update_account.await_args.kwargs) == {
            "full_name",
            "email",
            "language",
        }

    @pytest.mark.parametrize(
        "payload",
        [
            {"full_name": "   ", "email": "luc@simple-erp.fr"},
            {"full_name": "Luc", "email": "  "},
            {"full_name": "Luc"},
            {"email": "luc@simple-erp.fr"},
            {"full_name": "Luc", "email": "not-an-address"},
        ],
    )
    def test_an_invalid_payload_is_refused(self, payload: dict) -> None:
        """A blank name or a malformed address never reaches the service.

        Args:
            payload (dict): The body under test.
        """
        auth = MagicMock()
        auth.update_account = AsyncMock()

        response = _client(_user(), auth=auth).patch("/api/v1/me/account", json=payload)

        assert response.status_code == 422
        auth.update_account.assert_not_awaited()

    def test_an_address_another_account_uses_is_a_conflict(self) -> None:
        """Reported as a 409 rather than as a server fault.

        Notes:
            The column is unique, so without the service's own check this
            would surface as a database integrity error and be answered 500 —
            a spelling mistake reported as a crash, with nothing telling the
            holder what to correct.
        """
        auth = MagicMock()
        auth.update_account = AsyncMock(
            side_effect=MTAuthEmailAlreadyRegistered("Already registered.")
        )

        response = _client(_user(), auth=auth).patch(
            "/api/v1/me/account",
            json={"full_name": "Luc", "email": "taken@simple-erp.fr"},
        )

        assert response.status_code == 409


class TestMyAccountPhoto:
    """Tests for the portrait every signed-in account may set."""

    @pytest.mark.parametrize(
        "role,hca_id",
        [
            (UserRole.HCA, "hca-1"),
            (UserRole.MANAGER, None),
            (UserRole.ADMIN, None),
        ],
    )
    def test_every_role_may_upload_one(
        self, role: UserRole, hca_id: Optional[str]
    ) -> None:
        """**The gap this route exists to close.**

        Args:
            role (UserRole): The role signing in.
            hca_id (Optional[str]): The assistant record it is bound to.

        Notes:
            The only portrait route was ``PUT /me/hca/photo``, which refuses
            any account with no assistant record — every manager and every
            administrator. Their account screen showed a blank circle with
            nothing to click, so this asserts all three roles get an answer.
        """
        caller = _user(role, hca_id=hca_id)
        auth = MagicMock()
        auth.set_photo = AsyncMock(
            return_value=caller.model_copy(
                update={"photo_url": "https://cdn.example.com/hca-photos/u/a.jpg"}
            )
        )

        response = _client(caller, auth=auth).put(
            "/api/v1/me/account/photo",
            files={"photo": ("portrait.jpg", b"\xff\xd8\xffbytes", "image/jpeg")},
        )

        assert response.status_code == 200
        assert response.json()["photo_url"] == (
            "https://cdn.example.com/hca-photos/u/a.jpg"
        )

    def test_the_account_changed_is_the_callers_own(self) -> None:
        """There is no identifier in the path to point at somebody else.

        Notes:
            The service takes the ``User`` itself, so the only portrait a
            caller can replace is their own — the same shape
            ``PATCH /me/account`` uses.
        """
        caller = _user(user_id="user-7")
        auth = MagicMock()
        auth.set_photo = AsyncMock(return_value=caller)

        _client(caller, auth=auth).put(
            "/api/v1/me/account/photo",
            files={"photo": ("portrait.jpg", b"bytes", "image/jpeg")},
        )

        assert auth.set_photo.await_args.args[0] is caller

    def test_the_whole_file_reaches_the_service(self) -> None:
        """The bytes are read here, so the store can check them itself.

        Notes:
            The declared content type is not passed on: the store decides the
            format from the file's own leading bytes, because a client controls
            that header completely.
        """
        auth = MagicMock()
        auth.set_photo = AsyncMock(return_value=_user())

        _client(_user(), auth=auth).put(
            "/api/v1/me/account/photo",
            files={"photo": ("portrait.png", b"\x89PNG\r\n\x1a\nrest", "text/html")},
        )

        assert auth.set_photo.await_args.args[1] == b"\x89PNG\r\n\x1a\nrest"

    def test_an_image_the_store_refuses_is_answered_415(self) -> None:
        """A file that is not a JPEG, PNG or WebP is not stored."""
        auth = MagicMock()
        auth.set_photo = AsyncMock(
            side_effect=MTS3UnsupportedContentType("Not an image.")
        )

        response = _client(_user(), auth=auth).put(
            "/api/v1/me/account/photo",
            files={"photo": ("payload.svg", b"<svg/>", "image/svg+xml")},
        )

        assert response.status_code == 415

    def test_an_oversized_image_is_answered_413(self) -> None:
        """The configured limit is reported as a size failure, not a crash."""
        auth = MagicMock()
        auth.set_photo = AsyncMock(side_effect=MTS3PayloadTooLarge("Too big."))

        response = _client(_user(), auth=auth).put(
            "/api/v1/me/account/photo",
            files={"photo": ("portrait.jpg", b"x" * 32, "image/jpeg")},
        )

        assert response.status_code == 413

    def test_a_request_with_no_file_is_refused(self) -> None:
        """A portrait is uploaded as a file, never named as a URL."""
        auth = MagicMock()
        auth.set_photo = AsyncMock()

        response = _client(_user(), auth=auth).put(
            "/api/v1/me/account/photo",
            json={"photo_url": "https://evil.example.com/tracker.png"},
        )

        assert response.status_code == 422
        auth.set_photo.assert_not_awaited()

    def test_a_portrait_can_be_removed(self) -> None:
        """Removing one leaves the initials, which is a legible avatar."""
        caller = _user()
        auth = MagicMock()
        auth.clear_photo = AsyncMock(return_value=caller)

        response = _client(caller, auth=auth).delete("/api/v1/me/account/photo")

        assert response.status_code == 200
        assert response.json()["photo_url"] is None
        assert auth.clear_photo.await_args.args[0] is caller

    @pytest.mark.parametrize("method", ["put", "delete"])
    def test_the_password_hash_is_never_returned(self, method: str) -> None:
        """Both routes answer with an account; neither may carry a credential.

        Args:
            method (str): The verb under test.
        """
        auth = MagicMock()
        auth.set_photo = AsyncMock(return_value=_user())
        auth.clear_photo = AsyncMock(return_value=_user())
        client = _client(_user(), auth=auth)

        body = (
            client.put(
                "/api/v1/me/account/photo",
                files={"photo": ("portrait.jpg", b"bytes", "image/jpeg")},
            )
            if method == "put"
            else client.delete("/api/v1/me/account/photo")
        ).json()

        assert "hashed_password" not in body


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


class TestMyCompanyBankingDetails:
    """Tests for the bank account an administrator records on their agency."""

    def test_an_iban_and_bic_reach_the_service(self) -> None:
        """A customer told what to pay has to be told where to send it."""
        companies = MagicMock()
        companies.get = AsyncMock(return_value=_company())
        companies.update = AsyncMock(side_effect=lambda _id, company: company)

        response = _client(_user(UserRole.ADMIN), companies=companies).put(
            "/api/v1/me/company",
            json={
                "name": "Aide Domicile Paris",
                "iban": "FR76 3000 6000 0112 3456 7890 189",
                "bic": "bnpafrpp",
            },
        )

        assert response.status_code == 200
        written = companies.update.await_args.args[1]
        assert written.iban == "FR7630006000011234567890189"
        assert written.bic == "BNPAFRPP"

    def test_an_iban_that_fails_its_checksum_is_refused(self) -> None:
        """The model's rule is what the route enforces, and it answers 422.

        Notes:
            The digits are transposed, not missing — the payload satisfies
            every shape rule and fails only the check digits, which is exactly
            the mistake somebody makes copying an account number by hand.
        """
        companies = MagicMock()
        companies.get = AsyncMock(return_value=_company())
        companies.update = AsyncMock(side_effect=lambda _id, company: company)

        response = _client(_user(UserRole.ADMIN), companies=companies).put(
            "/api/v1/me/company",
            json={"name": "Aide Domicile Paris", "iban": "FR7630006000011234567809189"},
        )

        assert response.status_code == 422
        companies.update.assert_not_awaited()

    def test_the_administrator_reads_their_own_account_whole(self) -> None:
        """**The one route that hands back an unmasked IBAN.**

        Notes:
            An administrator has to be able to read it back to correct it. The
            agency routes a manager can reach return a masked projection
            instead — see the company-endpoint tests.
        """
        companies = MagicMock()
        companies.get = AsyncMock(
            return_value=_company().model_copy(
                update={"iban": "FR7630006000011234567890189"}
            )
        )

        response = _client(_user(UserRole.ADMIN), companies=companies).get(
            "/api/v1/me/company"
        )

        assert response.json()["iban"] == "FR7630006000011234567890189"

    def test_the_payload_cannot_carry_a_logo_url(self) -> None:
        """**The logo is written only by the route that uploads it.**

        Notes:
            Accepting one here would let a hand-crafted payload point the field
            at an image this application does not own — and the delete path
            would then be asked to remove an object belonging to somebody else.
        """
        existing = _company()
        companies = MagicMock()
        companies.get = AsyncMock(return_value=existing)
        companies.update = AsyncMock(side_effect=lambda _id, company: company)

        _client(_user(UserRole.ADMIN), companies=companies).put(
            "/api/v1/me/company",
            json={"name": "Renamed", "logo_url": "https://evil.example/x.png"},
        )

        assert companies.update.await_args.args[1].logo_url is None


class TestMyCompanyLogo:
    """Tests for the agency's visual identity."""

    def test_an_upload_is_handed_to_the_service_as_bytes(self) -> None:
        """The route reads the file and lets the service place it."""
        stored = _company().model_copy(
            update={
                "logo_url": (
                    "https://minio.internal/simple-erp/company-logos/company-1/a.png"
                )
            }
        )
        companies = MagicMock()
        companies.set_logo = AsyncMock(return_value=stored)

        response = _client(_user(UserRole.ADMIN), companies=companies).put(
            "/api/v1/me/company/logo",
            files={
                "logo": ("mark.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "image/png")
            },
        )

        assert response.status_code == 200
        assert response.json()["logo_url"] == stored.logo_url
        assert companies.set_logo.await_args.args[0] == "company-1"
        assert companies.set_logo.await_args.args[1].startswith(b"\x89PNG")

    def test_a_logo_can_be_removed(self) -> None:
        """Clearing hands back the agency with no image."""
        companies = MagicMock()
        companies.clear_logo = AsyncMock(return_value=_company())

        response = _client(_user(UserRole.ADMIN), companies=companies).delete(
            "/api/v1/me/company/logo"
        )

        assert response.status_code == 200
        assert response.json()["logo_url"] is None
        companies.clear_logo.assert_awaited_once_with("company-1")

    @pytest.mark.parametrize(
        "failure,expected",
        [
            pytest.param(MTS3PayloadTooLarge("too big"), 413, id="Too large"),
            pytest.param(
                MTS3UnsupportedContentType("not an image"), 415, id="Not an image"
            ),
        ],
    )
    def test_a_refused_upload_carries_its_own_status(
        self, failure: Exception, expected: int
    ) -> None:
        """The object store's refusals reach the client as themselves.

        Args:
            failure (Exception): What the service raises.
            expected (int): The status the handler maps it to.
        """
        companies = MagicMock()
        companies.set_logo = AsyncMock(side_effect=failure)

        response = _client(_user(UserRole.ADMIN), companies=companies).put(
            "/api/v1/me/company/logo",
            files={"logo": ("x.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        )

        assert response.status_code == expected

    @pytest.mark.parametrize("method", ["PUT", "DELETE"])
    def test_both_logo_routes_are_administrator_gated(self, method: str) -> None:
        """**A logo is how the agency identifies itself on every quote.**

        Args:
            method (str): The verb under test.

        Notes:
            Asserted against the route's declared dependencies, as the sibling
            company test explains: ``get_admin_user`` reads the account from
            request state, so calling the route on a bare client would answer
            500 for a reason that has nothing to do with the role.
        """
        matching = [
            route
            for route in me_router.routes
            if getattr(route, "path", None) == "/api/v1/me/company/logo"
            and method in getattr(route, "methods", set())
        ]
        assert matching, f"No {method} /api/v1/me/company/logo route is registered."

        guards = {
            dependency.call
            for dependency in matching[0].dependant.dependencies
            if dependency.call is not None
        }
        assert get_admin_user in guards
        assert get_current_user not in guards
