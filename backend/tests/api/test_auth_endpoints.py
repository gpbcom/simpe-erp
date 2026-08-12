from __future__ import annotations

# Standard library imports
from types import SimpleNamespace
from typing import Callable

from unittest.mock import AsyncMock, MagicMock

# Third-party imports
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_admin_user,
    get_auth_service,
    get_current_user,
    get_hca_user,
    get_customer_user,
    get_manager_user,
)
from api.exception_handlers import ExceptionHandlers
from api.v1.auth.auth import router as auth_router
from models.auth.access_token import AccessToken
from models.auth.user import User
from models.enums import UserRole
from models.schemas.exceptions import (
    MTInvalidLoginRequestException,
    MTInvalidRegisterRequestException,
)
from service.auth.exceptions import (
    MTAuthEmailAlreadyRegistered,
    MTAuthHcaLinkRequired,
    MTAuthInvalidCredentials,
    MTAuthUserInactive,
)
from tests.annotations import ModelInput


def _user(role: UserRole = UserRole.MANAGER, user_id: str = "user-1") -> User:
    """Build an account for a role.

    Args:
        role (UserRole): The role to grant.
        user_id (str): The identifier to assign.

    Returns:
        User: The account.
    """
    return User(
        company_id="company-1",
        id=user_id,
        email=f"{user_id}@example.com",
        full_name="Test Account",
        role=role,
        hca_id="hca-1" if role is UserRole.HCA else None,
    )


def _client(service: MagicMock, caller: User = None) -> TestClient:
    """Build a client for the auth router alone.

    Args:
        service (MagicMock): The stubbed authentication service.
        caller (User): The account the request is authenticated as, or ``None``
            to leave the request anonymous.

    Returns:
        TestClient: A client over an app mounting only the router under test.

    Notes:
        Every service dependency is replaced, so no database connection is
        attempted. An unmocked repository would make these tests hang on a
        connection attempt rather than fail fast.

        The production exception handlers are installed through the same
        registrar the application uses. The endpoints raise nothing themselves
        — a service's own exception travels to the handler — so a router
        mounted without them answers 500 for every failure it is supposed to
        turn into a 401, a 409 or a 422.
    """
    app = FastAPI()
    app.include_router(auth_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_auth_service] = lambda: service
    if caller is not None:
        app.dependency_overrides[get_current_user] = lambda: caller
    return TestClient(app)


class TestRegisterEndpoint:
    """Tests for POST /api/v1/auth/register."""

    def test_a_valid_registration_returns_201(self) -> None:
        """A created account comes back with a 201."""
        service = MagicMock()
        service.register = AsyncMock(return_value=_user(UserRole.MANAGER))
        response = _client(service).post(
            "/api/v1/auth/register",
            json={
                "email": "claire@example.com",
                "full_name": "Claire Bernard",
                "password": "a-long-enough-password",
                "hca_id": "hca-1",
            },
        )
        assert response.status_code == 201

    def test_the_response_never_carries_the_password_hash(self) -> None:
        """The credential must not leave the backend."""
        service = MagicMock()
        service.register = AsyncMock(return_value=_user(UserRole.MANAGER))
        response = _client(service).post(
            "/api/v1/auth/register",
            json={
                "email": "claire@example.com",
                "full_name": "Claire Bernard",
                "password": "a-long-enough-password",
                "hca_id": "hca-1",
            },
        )
        assert "hashed_password" not in response.json()

    def test_a_duplicate_address_returns_409(self) -> None:
        """Registering a known address is a conflict."""
        service = MagicMock()
        service.register = AsyncMock(
            side_effect=MTAuthEmailAlreadyRegistered("Already registered.")
        )
        response = _client(service).post(
            "/api/v1/auth/register",
            json={
                "email": "claire@example.com",
                "full_name": "Claire Bernard",
                "password": "a-long-enough-password",
                "hca_id": "hca-1",
            },
        )
        assert response.status_code == 409

    def test_an_unlinked_assistant_account_returns_422(self) -> None:
        """An assistant account must name its assistant record."""
        service = MagicMock()
        service.register = AsyncMock(
            side_effect=MTAuthHcaLinkRequired("Needs an assistant record.")
        )
        response = _client(service).post(
            "/api/v1/auth/register",
            json={
                "email": "luc@example.com",
                "full_name": "Luc Martin",
                "password": "a-long-enough-password",
                "hca_id": "hca-1",
            },
        )
        assert response.status_code == 422

    def test_a_short_password_is_rejected_with_422(self) -> None:
        """The request model's own exception becomes a 422, not a 500.

        Notes:
            This is what the stacked exception handler exists for. Without it
            the model's MT* exception escapes Pydantic untouched and FastAPI
            answers an opaque 500.
        """
        service = MagicMock()
        service.register = AsyncMock()
        response = _client(service).post(
            "/api/v1/auth/register",
            json={
                "email": "claire@example.com",
                "full_name": "Claire Bernard",
                "password": "short",
                "hca_id": "hca-1",
            },
        )
        assert response.status_code == 422
        service.register.assert_not_awaited()

    def test_the_error_message_never_echoes_the_password(self) -> None:
        """A rejected password must not be written into the response or logs."""
        service = MagicMock()
        service.register = AsyncMock()
        secret = "short"
        response = _client(service).post(
            "/api/v1/auth/register",
            json={
                "email": "claire@example.com",
                "full_name": "Claire Bernard",
                "password": secret,
                "hca_id": "hca-1",
            },
        )
        assert secret not in response.text

    def test_a_role_in_the_payload_is_ignored(self) -> None:
        """Public registration always grants the assistant role.

        Notes:
            **This is the test the whole route rests on.** Registration is the
            one way to create an account without already holding a credential.
            The payload used to carry a ``role``, which was passed straight to
            the service — so anybody who could reach the API could grant
            themselves ``admin`` by typing it into the request body. The field
            is gone, and a caller who sends one anyway is registered as an
            assistant like everybody else.
        """
        service = MagicMock()
        service.register = AsyncMock(return_value=_user(UserRole.HCA))
        response = _client(service).post(
            "/api/v1/auth/register",
            json={
                "email": "claire@example.com",
                "full_name": "Claire Bernard",
                "password": "a-long-enough-password",
                "hca_id": "hca-1",
                "role": "admin",
            },
        )

        assert response.status_code == 201
        assert service.register.await_args.kwargs["role"] is UserRole.HCA
        assert response.json()["role"] == "hca"


class TestLoginEndpoint:
    """Tests for POST /api/v1/auth/login."""

    def test_a_valid_sign_in_returns_a_token(self) -> None:
        """A successful sign-in yields a bearer token."""
        service = MagicMock()
        service.authenticate = AsyncMock(return_value=_user())
        service.issue_token = AsyncMock(
            return_value=AccessToken(access_token="a.b.c", expires_in=3600)
        )
        response = _client(service).post(
            "/api/v1/auth/login",
            json={"email": "claire@example.com", "password": "a-password"},
        )
        assert response.status_code == 200
        assert response.json() == {
            "access_token": "a.b.c",
            "token_type": "bearer",
            "expires_in": 3600,
        }

    def test_bad_credentials_return_401(self) -> None:
        """A wrong password is unauthorised."""
        service = MagicMock()
        service.authenticate = AsyncMock(
            side_effect=MTAuthInvalidCredentials("Incorrect email address or password.")
        )
        response = _client(service).post(
            "/api/v1/auth/login",
            json={"email": "claire@example.com", "password": "wrong"},
        )
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"

    def test_the_401_does_not_say_which_half_was_wrong(self) -> None:
        """The message must not distinguish an unknown address from a bad password.

        Notes:
            Distinguishing them would turn the endpoint into an
            account-enumeration oracle.
        """
        service = MagicMock()
        service.authenticate = AsyncMock(
            side_effect=MTAuthInvalidCredentials("Incorrect email address or password.")
        )
        response = _client(service).post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "wrong"},
        )
        detail = response.json()["detail"].lower()
        assert "not found" not in detail
        assert "unknown" not in detail
        assert "no account" not in detail

    def test_an_inactive_account_returns_403(self) -> None:
        """A deactivated account is told to contact an administrator."""
        service = MagicMock()
        service.authenticate = AsyncMock(
            side_effect=MTAuthUserInactive("This account is deactivated.")
        )
        response = _client(service).post(
            "/api/v1/auth/login",
            json={"email": "claire@example.com", "password": "a-password"},
        )
        assert response.status_code == 403

    def test_an_empty_password_is_rejected_with_422(self) -> None:
        """A blank credential never reaches the service."""
        service = MagicMock()
        service.authenticate = AsyncMock()
        response = _client(service).post(
            "/api/v1/auth/login",
            json={"email": "claire@example.com", "password": ""},
        )
        assert response.status_code == 422
        service.authenticate.assert_not_awaited()


class TestMeEndpoint:
    """Tests for GET /api/v1/auth/me."""

    def test_it_reports_the_signed_in_account(self) -> None:
        """The caller's own account comes back."""
        service = MagicMock()
        response = _client(service, caller=_user(UserRole.MANAGER)).get(
            "/api/v1/auth/me"
        )
        assert response.status_code == 200
        assert response.json()["role"] == "manager"

    def test_it_never_carries_the_password_hash(self) -> None:
        """The credential must not leave the backend."""
        service = MagicMock()
        response = _client(service, caller=_user()).get("/api/v1/auth/me")
        assert "hashed_password" not in response.json()

    def test_an_anonymous_caller_gets_401(self) -> None:
        """Without a credential the endpoint is unauthorised.

        Notes:
            ``/me`` is deliberately not exempt from authentication: it exists
            to report who the caller is, which is meaningless anonymously.
        """
        service = MagicMock()
        response = _client(service).get("/api/v1/auth/me")
        assert response.status_code == 401


def _customer_account() -> User:
    """Build a signed-in household's account.

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


class TestRoleGuards:
    """Tests for the role guards, exercised as plain functions."""

    def _request(self, user: User = None) -> SimpleNamespace:
        """Build a stub request carrying an account.

        Args:
            user (User): The account to attach, or ``None`` for anonymous.

        Returns:
            SimpleNamespace: A stand-in for a Starlette request.

        Notes:
            The guards take the request rather than a chain of dependencies,
            which is what lets them be tested with no application at all.
        """
        return SimpleNamespace(
            state=SimpleNamespace(user=user),
            headers={},
            method="GET",
            url=SimpleNamespace(path="/api/v1/test"),
        )

    @pytest.mark.parametrize(
        "guard",
        [
            get_current_user,
            get_hca_user,
            get_manager_user,
            get_admin_user,
            get_customer_user,
        ],
    )
    def test_every_guard_rejects_an_anonymous_request(self, guard: ModelInput) -> None:
        """No guard lets an unauthenticated caller through."""
        with pytest.raises(HTTPException) as raised:
            guard(self._request(None))
        assert raised.value.status_code == 401

    @pytest.mark.parametrize(
        ("role", "expected"),
        [
            pytest.param(UserRole.HCA, 200, id="hca passes"),
            pytest.param(UserRole.MANAGER, 403, id="manager is not an assistant"),
            pytest.param(UserRole.ADMIN, 403, id="admin is not an assistant"),
        ],
    )
    def test_the_assistant_guard_compares_by_identity(
        self, role: UserRole, expected: int
    ) -> None:
        """A manager outranks an assistant but holds no assistant record.

        Notes:
            Using rank here would let a manager through to a route that reads
            ``user.hca_id``, which they do not have.
        """
        request = self._request(_user(role))
        if expected == 200:
            assert get_hca_user(request).role is UserRole.HCA
            return
        with pytest.raises(HTTPException) as raised:
            get_hca_user(request)
        assert raised.value.status_code == 403

    @pytest.mark.parametrize(
        "role",
        [UserRole.HCA, UserRole.MANAGER, UserRole.ADMIN],
    )
    def test_no_employee_reaches_the_customer_guard(self, role: UserRole) -> None:
        """**The privacy gate, asserted on the guard itself.**

        Args:
            role (UserRole): The staff role that must be refused.

        Notes:
            An administrator outranks everybody and is still refused, because
            there is nothing to outrank: a customer is not a rung of the staff
            ladder. Written with ``has_at_least`` this guard would raise
            ``MTRoleNotRankable``; written the forgiving way it would admit
            every employee to a household's private space. Compared by identity,
            it does neither.
        """
        with pytest.raises(HTTPException) as raised:
            get_customer_user(self._request(_user(role)))

        assert raised.value.status_code == 403

    @pytest.mark.parametrize("guard", [get_manager_user, get_admin_user, get_hca_user])
    def test_a_customer_is_refused_every_staff_guard_with_a_403(
        self, guard: Callable[[Request], User]
    ) -> None:
        """**403, and never the enum's own 422.**

        Args:
            guard (Callable[[Request], User]): The staff guard under test.

        Notes:
            Found in a live run, not in a unit test. ``get_manager_user`` ranked
            the role before checking it was rankable, so a household reaching
            any manager route got ``MTRoleNotRankable`` — a **422 whose body
            explained the staff ladder**. Wrong twice over: 422 tells the client
            its request was malformed when it was fine, and the message leaks
            the reasoning.

            The three guards must agree. ``get_hca_user`` and
            ``get_admin_user`` compare by identity and were always right; the
            manager gate is the one that ranks.
        """
        with pytest.raises(HTTPException) as raised:
            guard(self._request(_customer_account()))

        assert raised.value.status_code == 403

    def test_a_customer_reaches_their_own_space(self) -> None:
        """The household's own account is the only one admitted."""
        customer = User(
            company_id="company-1",
            id="user-customer",
            email="marie@example.com",
            full_name="Marie Durand",
            role=UserRole.CUSTOMER,
            customer_id="customer-1",
        )

        admitted = get_customer_user(self._request(customer))

        assert admitted.role is UserRole.CUSTOMER
        assert admitted.customer_id == "customer-1"

    @pytest.mark.parametrize(
        ("role", "allowed"),
        [
            pytest.param(UserRole.HCA, False, id="hca denied"),
            pytest.param(UserRole.MANAGER, True, id="manager allowed"),
            pytest.param(UserRole.ADMIN, True, id="admin allowed"),
        ],
    )
    def test_the_manager_guard_uses_rank(self, role: UserRole, allowed: bool) -> None:
        """An administrator satisfies a manager gate."""
        request = self._request(_user(role))
        if allowed:
            assert get_manager_user(request).role is role
            return
        with pytest.raises(HTTPException) as raised:
            get_manager_user(request)
        assert raised.value.status_code == 403

    @pytest.mark.parametrize(
        ("role", "allowed"),
        [
            pytest.param(UserRole.HCA, False, id="hca denied"),
            pytest.param(UserRole.MANAGER, False, id="manager denied"),
            pytest.param(UserRole.ADMIN, True, id="admin allowed"),
        ],
    )
    def test_the_admin_guard_admits_only_admins(
        self, role: UserRole, allowed: bool
    ) -> None:
        """Running a planning and promoting a manager are admin-only."""
        request = self._request(_user(role))
        if allowed:
            assert get_admin_user(request).is_admin() is True
            return
        with pytest.raises(HTTPException) as raised:
            get_admin_user(request)
        assert raised.value.status_code == 403


class TestProductionRegistration:
    """The real application must carry what the isolated test app fakes."""

    def _production_app(self) -> ModelInput:
        """Import the real application.

        Returns:
            ModelInput: The configured FastAPI application.
        """
        # First-party imports
        from api.main import app

        return app

    def test_the_auth_router_is_mounted(self) -> None:
        """The endpoints exist on the real application."""
        client = TestClient(self._production_app())
        # An unauthenticated /me proves the route is mounted and guarded.
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_the_health_probe_answers_without_a_credential(self) -> None:
        """Liveness must not depend on being signed in."""
        client = TestClient(self._production_app())
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.parametrize(
        "exception_class",
        [MTInvalidLoginRequestException, MTInvalidRegisterRequestException],
    )
    def test_the_request_exceptions_are_mapped(self, exception_class: type) -> None:
        """A missing handler entry turns every 422 into an opaque 500."""
        assert exception_class in self._production_app().exception_handlers
