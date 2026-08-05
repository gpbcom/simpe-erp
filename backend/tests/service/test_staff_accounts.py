from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.configuration.auth_config import AuthConfig
from models.enums import AccountOrigin, ContractType, UserRole
from models.people.hca import Hca
from service.auth.auth import AuthService
from service.auth.exceptions import (
    MTAuthInvalidCredentials,
    MTAuthPasswordChangeRequired,
    MTAuthSamePassword,
    MTAuthUnknownHca,
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
        address={
            "street": "5 avenue de la Gare",
            "postal_code": "75012",
            "city": "Paris",
        },
        contract_type=ContractType.CDI,
    )


@pytest.fixture
def users() -> AsyncMock:
    """Return a stand-in account repository.

    Returns:
        AsyncMock: The repository double.
    """
    repository = AsyncMock()
    repository.create.side_effect = lambda user: user.model_copy(
        update={"id": "user-new"}
    )
    repository.update.side_effect = lambda user: user
    return repository


@pytest.fixture
def hcas() -> AsyncMock:
    """Return a stand-in assistant repository.

    Returns:
        AsyncMock: The repository double.
    """
    repository = AsyncMock()
    repository.get.return_value = _hca()
    return repository


@pytest.fixture
def service(users: AsyncMock, hcas: AsyncMock) -> AuthService:
    """Return an authentication service over stand-in repositories.

    Args:
        users (AsyncMock): The account repository double.
        hcas (AsyncMock): The assistant repository double.

    Returns:
        AuthService: The service under test.

    Notes:
        Hashing is not stubbed. What these tests turn on is whether a real
        credential verifies, so a double would prove nothing.
    """
    return AuthService(users=users, hcas=hcas, config=AuthConfig())


def _staff_account(
    auth: AuthService,
    password: str = "TemporaryPass123!",
    must_change: bool = True,
) -> User:
    """Build an account created by staff.

    Args:
        auth (AuthService): Used to hash the password.
        password (str): The password to hash.
        must_change (bool): Whether the change is still outstanding.

    Returns:
        User: The account.

    Notes:
        When the change is done, ``password_changed_at`` is set too. The model
        refuses a staff-created account that has neither the flag nor a
        recorded change — the two together are what say "the temporary password
        is no longer in force", and one without the other is a state that
        cannot honestly exist.
    """
    return User(
        id="user-1",
        email="new@example.com",
        full_name="New Starter",
        hashed_password=auth.hash(password),
        role=UserRole.HCA,
        hca_id="hca-1",
        account_origin=AccountOrigin.CREATED_BY_STAFF,
        must_change_password=must_change,
        password_changed_at=None if must_change else datetime.now(UTC),
    )


class TestTemporaryPassword:
    """Tests for the one-time password itself."""

    def test_it_generates_the_configured_length(self, service: AuthService) -> None:
        """A short temporary password is a guessable one."""
        assert (
            len(service.generate_temporary_password())
            == AuthService.TEMPORARY_PASSWORD_LENGTH
        )

    def test_two_passwords_differ(self, service: AuthService) -> None:
        """Every new starter gets their own."""
        generated = {service.generate_temporary_password() for _ in range(50)}

        assert len(generated) == 50

    def test_ambiguous_characters_are_excluded(self) -> None:
        """A password read down a telephone has to be transcribable.

        Notes:
            Not a security compromise: the remaining alphabet at sixteen
            characters carries far more entropy than any password a person
            would choose, and one that cannot be dictated gets reset three
            times instead.
        """
        assert not set(AuthService.TEMPORARY_PASSWORD_ALPHABET) & set("0O1lI")

    def test_it_draws_from_the_declared_alphabet(self, service: AuthService) -> None:
        """Nothing outside the alphabet can appear."""
        assert set(service.generate_temporary_password()) <= set(
            AuthService.TEMPORARY_PASSWORD_ALPHABET
        )


class TestStaffAccountCreation:
    """Tests for an administrator creating an assistant's account."""

    async def test_it_returns_the_password_once(self, service: AuthService) -> None:
        """The administrator has something to hand over."""
        user, password = await service.create_staff_account(
            email="new@example.com", full_name="New Starter", hca_id="hca-1"
        )

        assert user.id == "user-new"
        assert len(password) == AuthService.TEMPORARY_PASSWORD_LENGTH

    async def test_only_the_hash_is_stored(
        self, service: AuthService, users: AsyncMock
    ) -> None:
        """The plaintext exists in the response and nowhere else.

        Notes:
            An administrator who loses it regenerates rather than looks it up,
            which is the correct trade: the alternative is a table of readable
            passwords.
        """
        _, password = await service.create_staff_account(
            email="new@example.com", full_name="New Starter", hca_id="hca-1"
        )

        stored = users.create.await_args.args[0]
        assert stored.hashed_password != password
        assert service.verify(password, stored.hashed_password) is True

    async def test_the_account_must_change_its_password(
        self, service: AuthService, users: AsyncMock
    ) -> None:
        """The specification's "MANDATORY" starts here."""
        await service.create_staff_account(
            email="new@example.com", full_name="New Starter", hca_id="hca-1"
        )

        stored = users.create.await_args.args[0]
        assert stored.must_change_password is True
        assert stored.account_origin is AccountOrigin.CREATED_BY_STAFF

    async def test_an_unknown_assistant_is_refused(
        self, service: AuthService, hcas: AsyncMock
    ) -> None:
        """An account pointing at nothing could never be checked against a plan."""
        hcas.get.return_value = None

        with pytest.raises(MTAuthUnknownHca):
            await service.create_staff_account(
                email="new@example.com", full_name="New Starter", hca_id="ghost"
            )

    async def test_the_company_is_carried_onto_the_account(
        self, service: AuthService, users: AsyncMock
    ) -> None:
        """A staff-created account belongs to the agency that made it."""
        await service.create_staff_account(
            email="new@example.com",
            full_name="New Starter",
            hca_id="hca-1",
            company_id="company-1",
        )

        assert users.create.await_args.args[0].company_id == "company-1"


class TestMandatoryPasswordChange:
    """Tests for the rule that the temporary password must be replaced."""

    def test_an_account_that_must_change_is_refused(self, service: AuthService) -> None:
        """This is what makes the change mandatory rather than suggested.

        Notes:
            **The account can sign in — it has to, to change the password.**
            Without a check at every other request, it could then do everything
            else with a credential somebody else typed.
        """
        with pytest.raises(MTAuthPasswordChangeRequired):
            service.require_password_change_done(_staff_account(service))

    def test_an_account_that_has_changed_is_allowed(self, service: AuthService) -> None:
        """Once replaced, the account works normally.

        Notes:
            This is also what pins the invariant to a *representable* state.
            An earlier version keyed only on the origin and the flag, which
            meant a staff account could not be read back out of the database
            after changing its password — the validator refused the very state
            the change produced.
        """
        service.require_password_change_done(_staff_account(service, must_change=False))

    def test_a_self_registered_account_is_never_blocked(
        self, service: AuthService
    ) -> None:
        """Somebody who chose their own password has nothing to replace."""
        user = User(
            id="user-2",
            email="ana@example.com",
            full_name="Ana Lopez",
            hashed_password=service.hash("ChosenPassphrase!"),
            role=UserRole.HCA,
            hca_id="hca-1",
        )

        service.require_password_change_done(user)


class TestPasswordChange:
    """Tests for replacing a password."""

    async def test_a_correct_change_clears_the_flag(self, service: AuthService) -> None:
        """The account becomes usable at the moment it sets its own password."""
        updated = await service.change_password(
            _staff_account(service), "TemporaryPass123!", "MyOwnPassphrase99!"
        )

        assert updated.must_change_password is False
        assert service.verify("MyOwnPassphrase99!", updated.hashed_password) is True

    async def test_the_current_password_is_required(self, service: AuthService) -> None:
        """Being authenticated is not enough to change the password.

        Notes:
            A token left on a shared machine is exactly the case where somebody
            else would change the password, and knowing the old one is what
            tells the holder apart from whoever found the session.
        """
        with pytest.raises(MTAuthInvalidCredentials):
            await service.change_password(
                _staff_account(service), "WrongPassword!", "MyOwnPassphrase99!"
            )

    async def test_the_flag_survives_a_failed_change(
        self, service: AuthService, users: AsyncMock
    ) -> None:
        """A wrong guess does not unlock the account."""
        with pytest.raises(MTAuthInvalidCredentials):
            await service.change_password(
                _staff_account(service), "WrongPassword!", "MyOwnPassphrase99!"
            )

        users.update.assert_not_called()

    async def test_reusing_the_temporary_password_is_refused(
        self, service: AuthService
    ) -> None:
        """ "Changing" it to itself would clear the flag and change nothing.

        Notes:
            This matters most on exactly this path: the temporary password is
            one a second person has seen, so leaving it live while recording it
            as changed is the worst of both.
        """
        with pytest.raises(MTAuthSamePassword):
            await service.change_password(
                _staff_account(service), "TemporaryPass123!", "TemporaryPass123!"
            )

    async def test_an_account_with_no_credential_cannot_change_one(
        self, service: AuthService
    ) -> None:
        """A half-built account is refused rather than given a password."""
        user = User(
            id="user-3",
            email="nobody@example.com",
            full_name="Nobody",
            role=UserRole.MANAGER,
        )

        with pytest.raises(MTAuthInvalidCredentials):
            await service.change_password(user, "anything", "MyOwnPassphrase99!")
