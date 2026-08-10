from __future__ import annotations

# Standard library imports
from typing import get_args
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import get_company_service, get_manager_user
from api.exception_handlers import ExceptionHandlers
from api.v1.companies.companies import router as companies_router
from models.auth.user import User
from models.companies.company import Company
from models.enums import UserRole
from models.schemas.responses.companies.company_view import CompanyView

COMPANY_ID = "company-1"
IBAN = "FR7630006000011234567890189"


def _agency() -> Company:
    """Build a stored agency carrying a bank account.

    Returns:
        Company: The agency.
    """
    return Company(
        id=COMPANY_ID,
        name="Aide Domicile Paris",
        registration_number="12345678900011",
        iban=IBAN,
        bic="BNPAFRPP",
    )


def _caller(role: UserRole) -> User:
    """Build an authenticated account.

    Args:
        role (UserRole): The role it holds.

    Returns:
        User: The account.
    """
    return User(
        id="user-1",
        email=f"{role.value}@simple-erp.fr",
        full_name="Camille Fournier",
        hashed_password="$2b$12$abcdefghijklmnopqrstuv",
        role=role,
        company_id=COMPANY_ID,
    )


def _client(caller: User, service: MagicMock) -> TestClient:
    """Build a client whose guard resolves to a given account.

    Args:
        caller (User): The account the manager guard hands back.
        service (MagicMock): The company service double.

    Returns:
        TestClient: The client.

    Notes:
        ``get_manager_user`` is overridden rather than exercised. It reads the
        account from request state, which the middleware sets and a bare test
        client does not — so leaving it in place would answer 500 for a reason
        that has nothing to do with what is being tested here.
    """
    app = FastAPI()
    app.include_router(companies_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_company_service] = lambda: service
    app.dependency_overrides[get_manager_user] = lambda: caller
    return TestClient(app)


@pytest.fixture
def service() -> MagicMock:
    """Return a company service double holding one agency.

    Returns:
        MagicMock: The double.
    """
    double = MagicMock()
    double.get = AsyncMock(return_value=_agency())
    double.list = AsyncMock(return_value=[_agency()])
    return double


class TestReadingAnAgencyAsAManager:
    """Tests for what a manager is allowed to see of an agency."""

    def test_the_account_is_masked(self, service: MagicMock) -> None:
        """**A manager runs the week; they do not need the bank account.**

        Args:
            service (MagicMock): The company service double.

        Notes:
            The assertion that matters is the negative one. Checking the
            country code survives would pass on a response that masked nothing
            — what makes this a protection is that the middle is gone.
        """
        response = _client(_caller(UserRole.MANAGER), service).get(
            f"/api/v1/companies/{COMPANY_ID}"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["iban"] != IBAN
        assert IBAN[4:-4] not in body["iban"]
        assert body["iban_is_masked"] is True

    def test_the_listing_masks_too(self, service: MagicMock) -> None:
        """One agency or fifty, the rule is the same.

        Args:
            service (MagicMock): The company service double.
        """
        response = _client(_caller(UserRole.MANAGER), service).get("/api/v1/companies")

        assert response.status_code == 200
        assert response.json()[0]["iban"] != IBAN

    def test_everything_else_still_comes_back(self, service: MagicMock) -> None:
        """Masking the account must not read as data loss.

        Args:
            service (MagicMock): The company service double.
        """
        body = (
            _client(_caller(UserRole.MANAGER), service)
            .get(f"/api/v1/companies/{COMPANY_ID}")
            .json()
        )

        assert body["name"] == "Aide Domicile Paris"
        assert body["registration_number"] == "12345678900011"
        assert body["bic"] == "BNPAFRPP"


class TestReadingAnAgencyAsAnAdministrator:
    """Tests for the caller entitled to the whole record."""

    def test_the_account_comes_back_whole(self, service: MagicMock) -> None:
        """An administrator has to read it back to correct it.

        Args:
            service (MagicMock): The company service double.
        """
        body = (
            _client(_caller(UserRole.ADMIN), service)
            .get(f"/api/v1/companies/{COMPANY_ID}")
            .json()
        )

        assert body["iban"] == IBAN
        assert body["iban_is_masked"] is False

    def test_the_listing_is_whole_too(self, service: MagicMock) -> None:
        """The same decision on both read routes.

        Args:
            service (MagicMock): The company service double.
        """
        body = _client(_caller(UserRole.ADMIN), service).get("/api/v1/companies").json()

        assert body[0]["iban"] == IBAN


class TestTheShapeIsThePermission:
    """Tests that the masking cannot be undone by a change to the service."""

    def test_the_read_routes_do_not_return_a_whole_company(self) -> None:
        """**The protection is the response model, not the handler.**

        Notes:
            Both manager-facing routes declare ``CompanyView``. However the
            service changes, they physically cannot hand back a
            :class:`~models.companies.company.Company` — which is what would
            put an unmasked account number on the wire.
        """
        for path in ("/api/v1/companies", "/api/v1/companies/{company_id}"):
            matching = [
                route
                for route in companies_router.routes
                if getattr(route, "path", None) == path
                and "GET" in getattr(route, "methods", set())
            ]
            assert matching, f"No GET {path} route is registered."
            model = matching[0].response_model
            carried = {model, *get_args(model)}
            assert CompanyView in carried, (
                f"GET {path} returns {model!r}, not a CompanyView."
            )
            assert Company not in carried, (
                f"GET {path} returns a whole Company, account number included."
            )
