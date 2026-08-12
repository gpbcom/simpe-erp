from __future__ import annotations

# Standard library imports
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import get_company_registration_service
from api.exception_handlers import ExceptionHandlers
from api.middleware.auth_middleware import AuthMiddleware
from api.v1.companies.companies import router as companies_router
from models.auth.user import User
from models.organisation.companies.company import Company
from models.enums import UserRole
from service.auth.exceptions import MTAuthEmailAlreadyRegistered
from service.companies.exceptions import (
    MTCompanyNameTaken,
    MTCompanyRegistrationDisabled,
)

NEW_COMPANY_ID = "company-new"
PATH = "/api/v1/companies/registration"

PAYLOAD = {
    "company_name": "Aide et Presence Lyon",
    "full_name": "Camille Fournier",
    "email": "camille@aide-lyon.fr",
    "password": "a-founder-password-2026",
}


def _company() -> Company:
    """Build the stored company.

    Returns:
        Company: The company.
    """
    return Company(id=NEW_COMPANY_ID, name="Aide et Presence Lyon")


def _administrator() -> User:
    """Build the stored founder account.

    Returns:
        User: The account.
    """
    return User(
        id="user-founder",
        email="camille@aide-lyon.fr",
        full_name="Camille Fournier",
        hashed_password="$2b$12$stored",
        role=UserRole.ADMIN,
        company_id=NEW_COMPANY_ID,
    )


def _client(service: MagicMock) -> TestClient:
    """Build a client over the companies router.

    Args:
        service (MagicMock): The registration service double.

    Returns:
        TestClient: The client.
    """
    app = FastAPI()
    app.include_router(companies_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_company_registration_service] = lambda: service
    return TestClient(app)


@pytest.fixture
def service() -> MagicMock:
    """Return a registration service double that succeeds.

    Returns:
        MagicMock: The double.
    """
    double = MagicMock()
    double.register = AsyncMock(return_value=(_company(), _administrator()))
    return double


class TestFoundingAnAgencyOverHttp:
    """Tests for the public registration route."""

    def test_a_founder_gets_an_agency_and_an_administrator_account(
        self, service: MagicMock
    ) -> None:
        """The ordinary case answers 201 with both halves."""
        response = _client(service).post(PATH, json=PAYLOAD)

        assert response.status_code == 201
        body = response.json()
        assert body["company"]["name"] == "Aide et Presence Lyon"
        assert body["administrator"]["role"] == "admin"
        assert body["administrator"]["company_id"] == NEW_COMPANY_ID

    def test_the_password_hash_never_leaves(self, service: MagicMock) -> None:
        """The response is a UserResponse for exactly this reason."""
        response = _client(service).post(PATH, json=PAYLOAD)

        assert "hashed_password" not in response.json()["administrator"]

    def test_no_token_comes_back(self, service: MagicMock) -> None:
        """Founding an agency and holding a session are separate things.

        Notes:
            Issuing one here would be a second place that mints credentials,
            and so a second place to get expiry, scope and revocation wrong.
            The founder signs in through the ordinary login route.
        """
        body = _client(service).post(PATH, json=PAYLOAD).json()

        assert "access_token" not in body
        assert set(body) == {"company", "administrator"}

    def test_a_taken_address_is_a_conflict(self, service: MagicMock) -> None:
        """Answered as 409, naming the clash rather than a constraint."""
        service.register.side_effect = MTAuthEmailAlreadyRegistered("Taken.")

        response = _client(service).post(PATH, json=PAYLOAD)

        assert response.status_code == 409

    def test_a_taken_company_name_is_a_conflict(self, service: MagicMock) -> None:
        """Two agencies trading under one name cannot be told apart."""
        service.register.side_effect = MTCompanyNameTaken("Taken.")

        response = _client(service).post(PATH, json=PAYLOAD)

        assert response.status_code == 409

    def test_a_disabled_deployment_looks_like_no_such_route(
        self, service: MagicMock
    ) -> None:
        """404, not 403.

        Notes:
            A 403 confirms the feature exists and is merely switched off, which
            invites somebody to keep checking whether it has been switched on.
        """
        service.register.side_effect = MTCompanyRegistrationDisabled("Closed.")

        response = _client(service).post(PATH, json=PAYLOAD)

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "field,value",
        [
            pytest.param("company_name", "   ", id="Refused - blank company"),
            pytest.param("full_name", "", id="Refused - blank founder"),
            pytest.param("email", "  ", id="Refused - blank address"),
            pytest.param("password", "short", id="Refused - short password"),
            pytest.param("password", "a" * 73, id="Refused - past bcrypt"),
        ],
    )
    def test_a_malformed_payload_is_refused(
        self, service: MagicMock, field: str, value: str
    ) -> None:
        """Named at the boundary, as a 422, before anything is written.

        Args:
            service (MagicMock): The registration service double.
            field (str): The field to spoil.
            value (str): The value to spoil it with.
        """
        payload = {**PAYLOAD, field: value}

        response = _client(service).post(PATH, json=payload)

        assert response.status_code == 422
        service.register.assert_not_awaited()

    def test_a_role_in_the_payload_reaches_nothing(self, service: MagicMock) -> None:
        """The service is called without it, whatever the caller sent.

        Notes:
            This is the escalation the route has to be immune to. The payload
            model has no ``role`` field, so a caller naming one is ignored
            rather than obeyed.
        """
        _client(service).post(PATH, json={**PAYLOAD, "role": "admin"})

        assert "role" not in service.register.await_args.kwargs

    def test_a_company_id_in_the_payload_reaches_nothing(
        self, service: MagicMock
    ) -> None:
        """A founder cannot attach themselves to an agency that exists."""
        _client(service).post(PATH, json={**PAYLOAD, "company_id": "company-seeded"})

        assert "company_id" not in service.register.await_args.kwargs


class TestTheRouteIsPublic:
    """Tests for the authentication middleware's exemption."""

    def test_founding_an_agency_needs_no_credential(self) -> None:
        """Somebody with no account is exactly who this route is for."""
        assert PATH in AuthMiddleware.PUBLIC_POST_PATHS

    def test_only_the_exact_path_is_exempt(self) -> None:
        """The prefix stays closed.

        Notes:
            - Creating an agency as a manager, listing them, reading one,
              editing one and opening or closing its applications all live
              under ``/api/v1/companies`` and all stay behind a gate. A prefix
              exemption would have opened every one of them; matching the exact
              path is what keeps that from happening.
            - ``/choices`` is exempt for its own, older reason — an applicant
              with no account cannot pick a company without seeing the list —
              and is asserted here so the two exemptions are not confused for
              one prefix.
        """
        middleware = AuthMiddleware(app=None)

        assert middleware._is_exempt(PATH, "POST") is True
        assert middleware._is_exempt("/api/v1/companies", "POST") is False
        assert middleware._is_exempt("/api/v1/companies/registrations", "POST") is False
        assert middleware._is_exempt("/api/v1/companies/company-1", "GET") is False

    def test_the_exemption_is_for_post_only(self) -> None:
        """Reading is not founding.

        Notes:
            The same care the applications route takes: submitting is public,
            and anything else behind the path is not.
        """
        middleware = AuthMiddleware(app=None)

        assert middleware._is_exempt(PATH, "GET") is False
        assert middleware._is_exempt(PATH, "DELETE") is False
