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
from service.auth.auth import AuthService
from service.auth.exceptions import MTAuthLastAdmin, MTAuthUnknownAccount
from service.companies.companies import CompanyService
from service.companies.exceptions import MTCompanyNotEmpty
from storage.repositories.companies.company import CompanyRepository

COMPANY_ID = "company-1"


def _account(user_id: str = "user-1", role: UserRole = UserRole.ADMIN) -> User:
    """Build an account.

    Args:
        user_id (str): The identifier.
        role (UserRole): The role it holds.

    Returns:
        User: The account.
    """
    return User(
        id=user_id,
        email=f"{user_id}@simple-erp.fr",
        full_name="Camille Fournier",
        hashed_password="$2b$12$stored",
        role=role,
        company_id=COMPANY_ID,
    )


@pytest.fixture
def companies() -> MagicMock:
    """Return a company repository double holding one agency.

    Returns:
        MagicMock: The double.
    """
    repository = MagicMock(spec=CompanyRepository)
    repository.get = AsyncMock(return_value=Company(id=COMPANY_ID, name="Aide Lyon"))
    repository.delete = AsyncMock(return_value=True)
    return repository


@pytest.fixture
def users() -> MagicMock:
    """Return an account repository double reporting an empty agency.

    Returns:
        MagicMock: The double.
    """
    repository = MagicMock()
    repository.count_for_company = AsyncMock(return_value=0)
    return repository


@pytest.fixture
def hcas() -> MagicMock:
    """Return an assistant repository double reporting an empty agency.

    Returns:
        MagicMock: The double.
    """
    repository = MagicMock()
    repository.count_for_company = AsyncMock(return_value=0)
    return repository


@pytest.fixture
def service(companies: MagicMock, users: MagicMock, hcas: MagicMock) -> CompanyService:
    """Return a company service over the doubles.

    Args:
        companies (MagicMock): The company store double.
        users (MagicMock): The account store double.
        hcas (MagicMock): The assistant store double.

    Returns:
        CompanyService: The service under test.
    """
    return CompanyService(companies=companies, users=users, hcas=hcas)


class TestDeletingAnAgency:
    """Tests for removing an agency, and refusing to.

    Notes:
        Every account and every assistant names the agency they belong to, and
        that link is required rather than optional. Removing an agency somebody
        still points at would leave rows nothing can rebuild.
    """

    async def test_an_empty_agency_is_removed(
        self, service: CompanyService, companies: MagicMock
    ) -> None:
        """The case this exists for: an agency founded in error."""
        await service.delete(COMPANY_ID)

        companies.delete.assert_awaited_once_with(COMPANY_ID)

    async def test_an_agency_with_an_account_is_refused(
        self, service: CompanyService, users: MagicMock, companies: MagicMock
    ) -> None:
        """And nothing is deleted."""
        users.count_for_company.return_value = 2

        with pytest.raises(MTCompanyNotEmpty):
            await service.delete(COMPANY_ID)

        companies.delete.assert_not_awaited()

    async def test_an_agency_with_an_assistant_is_refused(
        self, service: CompanyService, hcas: MagicMock, companies: MagicMock
    ) -> None:
        """An assistant counts as much as an account.

        Notes:
            Both tables carry a required ``company_id``. Checking only the
            accounts would let an agency be removed out from under its
            workforce.
        """
        hcas.count_for_company.return_value = 1

        with pytest.raises(MTCompanyNotEmpty):
            await service.delete(COMPANY_ID)

        companies.delete.assert_not_awaited()

    async def test_the_refusal_names_what_is_still_attached(
        self, service: CompanyService, users: MagicMock, hcas: MagicMock
    ) -> None:
        """So the caller knows which table to look in.

        Notes:
            "Cannot delete" leaves somebody guessing between three tables. The
            counts tell them what to do next.
        """
        users.count_for_company.return_value = 2
        hcas.count_for_company.return_value = 3

        with pytest.raises(MTCompanyNotEmpty) as refusal:
            await service.delete(COMPANY_ID)

        assert "2 account(s)" in str(refusal.value)
        assert "3 assistant(s)" in str(refusal.value)


class TestDeletingAnAccount:
    """Tests for removing an account, and refusing to."""

    @pytest.fixture
    def accounts(self) -> MagicMock:
        """Return an account repository double.

        Returns:
            MagicMock: The double.
        """
        repository = MagicMock()
        repository.get = AsyncMock(return_value=_account("user-2"))
        repository.count_admins = AsyncMock(return_value=3)
        repository.delete = AsyncMock(return_value=True)
        return repository

    @pytest.fixture
    def auth(self, accounts: MagicMock) -> AuthService:
        """Return an authentication service over the double.

        Args:
            accounts (MagicMock): The account store double.

        Returns:
            AuthService: The service under test.
        """
        return AuthService(users=accounts, hcas=MagicMock(), config=AuthConfig())

    async def test_an_ordinary_account_is_removed(
        self, auth: AuthService, accounts: MagicMock
    ) -> None:
        """The case this exists for: an account raised in error."""
        await auth.delete_account("user-2", requested_by=_account("user-1"))

        accounts.delete.assert_awaited_once_with("user-2")

    async def test_an_administrator_may_not_delete_themselves(
        self, auth: AuthService, accounts: MagicMock
    ) -> None:
        """Locking yourself out is not recoverable through the product."""
        with pytest.raises(MTAuthLastAdmin):
            await auth.delete_account("user-1", requested_by=_account("user-1"))

        accounts.delete.assert_not_awaited()

    async def test_the_last_administrator_cannot_be_deleted(
        self, auth: AuthService, accounts: MagicMock
    ) -> None:
        """An agency with no administrator cannot appoint one.

        Notes:
            The same rule demotion and deactivation already enforce, applied to
            the one operation that had no guard at all.
        """
        accounts.count_admins.return_value = 1

        with pytest.raises(MTAuthLastAdmin):
            await auth.delete_account("user-2", requested_by=_account("user-1"))

        accounts.delete.assert_not_awaited()

    async def test_a_manager_is_removable_even_as_the_last_admin_stands(
        self, auth: AuthService, accounts: MagicMock
    ) -> None:
        """The guard is about administrators, not about everybody."""
        accounts.get.return_value = _account("user-2", role=UserRole.MANAGER)
        accounts.count_admins.return_value = 1

        await auth.delete_account("user-2", requested_by=_account("user-1"))

        accounts.delete.assert_awaited_once_with("user-2")

    async def test_an_account_that_is_not_there_is_reported(
        self, auth: AuthService, accounts: MagicMock
    ) -> None:
        """Absence is an error, not a silent success."""
        accounts.get.return_value = None

        with pytest.raises(MTAuthUnknownAccount):
            await auth.delete_account("user-9", requested_by=_account("user-1"))
