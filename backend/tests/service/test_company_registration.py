from __future__ import annotations

# Standard library imports
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.companies.company import Company
from models.configuration.auth_config import AuthConfig
from models.enums import UserRole
from service.companies.exceptions import (
    MTCompanyNameTaken,
    MTCompanyRegistrationDisabled,
)
from service.companies.registration import CompanyRegistrationService

NEW_COMPANY_ID = "company-new"
EXISTING_COMPANY_ID = "company-seeded"


def _company(company_id: str = NEW_COMPANY_ID) -> Company:
    """Build a stored company.

    Args:
        company_id (str): The identifier it was stored under.

    Returns:
        Company: The company.
    """
    return Company(id=company_id, name="Aide et Presence Lyon")


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


@pytest.fixture
def companies() -> MagicMock:
    """Return a company service double.

    Returns:
        MagicMock: The double.
    """
    service = MagicMock()
    service.create = AsyncMock(return_value=_company())
    return service


@pytest.fixture
def auth() -> MagicMock:
    """Return an authentication service double.

    Returns:
        MagicMock: The double.
    """
    service = MagicMock()
    service.register = AsyncMock(return_value=_administrator())
    return service


@pytest.fixture
def publisher() -> MagicMock:
    """Return a broker publisher double that confirms.

    Returns:
        MagicMock: The double.
    """
    double = MagicMock()
    double.publish = AsyncMock(return_value=True)
    return double


@pytest.fixture
def service(
    companies: MagicMock, auth: MagicMock, publisher: MagicMock
) -> CompanyRegistrationService:
    """Return a registration service with the feature enabled.

    Args:
        companies (MagicMock): The company service double.
        auth (MagicMock): The authentication service double.
        publisher (MagicMock): The broker publisher double.

    Returns:
        CompanyRegistrationService: The service under test.
    """
    return CompanyRegistrationService(
        companies=companies,
        auth=auth,
        publisher=publisher,
        config=AuthConfig(allow_company_registration=True),
    )


class TestFoundingAnAgency:
    """Tests for the ordinary case."""

    async def test_the_company_and_its_administrator_are_created(
        self, service: CompanyRegistrationService
    ) -> None:
        """Both halves land, and the account names the company."""
        company, administrator = await service.register(
            company_name="Aide et Presence Lyon",
            full_name="Camille Fournier",
            email="camille@aide-lyon.fr",
            password="a-founder-password-2026",
        )

        assert company.id == NEW_COMPANY_ID
        assert administrator.company_id == NEW_COMPANY_ID

    async def test_the_company_is_written_before_the_account(
        self,
        service: CompanyRegistrationService,
        companies: MagicMock,
        auth: MagicMock,
    ) -> None:
        """The account names the company, so the company has to exist first.

        Notes:
            The ordering is what lets a failed account take the company with
            it: the request fails as a whole and its transaction rolls back,
            rather than leaving an agency nobody can sign in to.
        """
        await service.register(
            company_name="Aide et Presence Lyon",
            full_name="Camille Fournier",
            email="camille@aide-lyon.fr",
            password="a-founder-password-2026",
        )

        assert auth.register.await_args.kwargs["company_id"] == NEW_COMPANY_ID
        assert companies.create.await_count == 1

    async def test_the_new_agency_accepts_applications(
        self, service: CompanyRegistrationService, companies: MagicMock
    ) -> None:
        """Founding one and finding nobody can apply would be a puzzle."""
        await service.register(
            company_name="Aide et Presence Lyon",
            full_name="Camille Fournier",
            email="camille@aide-lyon.fr",
            password="a-founder-password-2026",
        )

        stored = companies.create.await_args.args[0]
        assert stored.is_accepting_applications is True

    async def test_the_founder_is_not_asked_to_change_their_password(
        self, service: CompanyRegistrationService, auth: MagicMock
    ) -> None:
        """They chose it a moment ago; there is nothing to protect against."""
        await service.register(
            company_name="Aide et Presence Lyon",
            full_name="Camille Fournier",
            email="camille@aide-lyon.fr",
            password="a-founder-password-2026",
        )

        assert "must_change_password" not in auth.register.await_args.kwargs


class TestFoundingAnAgencyIsPrivileged:
    """Tests for the rights this grants, and their limits."""

    async def test_the_founder_is_made_an_administrator(
        self, service: CompanyRegistrationService, auth: MagicMock
    ) -> None:
        """The whole point of the route."""
        await service.register(
            company_name="Aide et Presence Lyon",
            full_name="Camille Fournier",
            email="camille@aide-lyon.fr",
            password="a-founder-password-2026",
        )

        assert auth.register.await_args.kwargs["role"] is UserRole.ADMIN

    async def test_the_role_cannot_be_chosen_by_the_caller(
        self, service: CompanyRegistrationService
    ) -> None:
        """There is no parameter for it, and that is the guard.

        Notes:
            An unauthenticated route that honoured a role from its caller would
            hand out administrator rights to whoever asked. The role is written
            by the service, so there is nothing to smuggle.
        """
        with pytest.raises(TypeError):
            await service.register(
                company_name="Aide et Presence Lyon",
                full_name="Camille Fournier",
                email="camille@aide-lyon.fr",
                password="a-founder-password-2026",
                role=UserRole.ADMIN,
            )

    async def test_an_existing_company_cannot_be_named(
        self, service: CompanyRegistrationService
    ) -> None:
        """Founding an agency must not be a way into somebody else's.

        Notes:
            The administrator rights are only defensible because the company is
            new. A parameter naming an existing one would turn this route into
            a takeover, so there is no such parameter.
        """
        with pytest.raises(TypeError):
            await service.register(
                company_name="Aide et Presence Lyon",
                full_name="Camille Fournier",
                email="camille@aide-lyon.fr",
                password="a-founder-password-2026",
                company_id=EXISTING_COMPANY_ID,
            )

    async def test_a_clashing_company_name_is_refused(
        self, service: CompanyRegistrationService, companies: MagicMock, auth: MagicMock
    ) -> None:
        """And no account is created for an agency that was not.

        Notes:
            The account is only attempted once the company exists, so a refusal
            here leaves nothing behind to clean up.
        """
        companies.create.side_effect = MTCompanyNameTaken("Taken.")

        with pytest.raises(MTCompanyNameTaken):
            await service.register(
                company_name="Aide et Presence Paris",
                full_name="Camille Fournier",
                email="camille@aide-lyon.fr",
                password="a-founder-password-2026",
            )

        auth.register.assert_not_awaited()


class TestFoundingAnAgencyIsOptIn:
    """Tests for the feature flag."""

    def test_it_is_closed_by_default(
        self, companies: MagicMock, auth: MagicMock
    ) -> None:
        """A deployment gets the safe posture by standing the service up.

        Notes:
            A company is not a tenancy boundary here, so an administrator
            minted by public sign-up reads every agency's records. Off unless
            asked for is the only defensible default until that changes.
        """
        service = CompanyRegistrationService(
            companies=companies,
            auth=auth,
            publisher=MagicMock(publish=AsyncMock(return_value=True)),
            config=AuthConfig(),
        )

        assert service.is_open() is False

    async def test_a_closed_deployment_refuses_and_writes_nothing(
        self, companies: MagicMock, auth: MagicMock
    ) -> None:
        """Neither half is created when the door is shut."""
        service = CompanyRegistrationService(
            companies=companies,
            auth=auth,
            publisher=MagicMock(publish=AsyncMock(return_value=True)),
            config=AuthConfig(),
        )

        with pytest.raises(MTCompanyRegistrationDisabled):
            await service.register(
                company_name="Aide et Presence Lyon",
                full_name="Camille Fournier",
                email="camille@aide-lyon.fr",
                password="a-founder-password-2026",
            )

        companies.create.assert_not_awaited()
        auth.register.assert_not_awaited()

    def test_it_is_open_when_the_deployment_opts_in(
        self, service: CompanyRegistrationService
    ) -> None:
        """The demonstration stack turns it on knowingly."""
        assert service.is_open() is True
