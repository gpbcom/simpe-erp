from __future__ import annotations

# Standard library imports
# Third-party imports
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.auth.user import User
from models.enums import UserRole
from models.people.hca import Hca
from storage.repositories.hca import HcaRepository
from storage.repositories.user import UserRepository


@pytest.fixture
def manager() -> User:
    """Return an unsaved manager account.

    Returns:
        User: A manager with a password hash.
    """
    return User(
        email="claire.bernard@example.com",
        full_name="Claire Bernard",
        role=UserRole.MANAGER,
        hashed_password="$2b$12$notarealhash",
    )


class TestUserRepository:
    """Tests for the UserRepository."""

    # ------------------------------------------------------------------ #
    #  Create and read
    # ------------------------------------------------------------------ #

    async def test_create_assigns_an_identifier(
        self, session: AsyncSession, manager: User
    ) -> None:
        """A stored account comes back with a generated identifier."""
        stored = await UserRepository(session).create(manager)
        assert stored.id is not None

    async def test_round_trip_preserves_the_role(
        self, session: AsyncSession, manager: User
    ) -> None:
        """The role is what every access decision is made from."""
        repository = UserRepository(session)
        stored = await repository.create(manager)
        loaded = await repository.get(stored.id)
        assert loaded is not None
        assert loaded.role is UserRole.MANAGER
        assert loaded.is_manager() is True
        assert loaded.is_admin() is False

    async def test_get_returns_none_for_an_unknown_id(
        self, session: AsyncSession
    ) -> None:
        """An absent account reads as None."""
        assert await UserRepository(session).get("no-such-id") is None

    # ------------------------------------------------------------------ #
    #  get_by_email — the sign-in path
    # ------------------------------------------------------------------ #

    async def test_get_by_email_finds_the_account(
        self, session: AsyncSession, manager: User
    ) -> None:
        """Sign-in looks the account up by address."""
        repository = UserRepository(session)
        await repository.create(manager)
        found = await repository.get_by_email("claire.bernard@example.com")
        assert found is not None
        assert found.full_name == "Claire Bernard"

    async def test_get_by_email_is_case_insensitive(
        self, session: AsyncSession, manager: User
    ) -> None:
        """A differently capitalised sign-in still finds the account."""
        repository = UserRepository(session)
        await repository.create(manager)
        found = await repository.get_by_email("  Claire.Bernard@EXAMPLE.com  ")
        assert found is not None

    async def test_get_by_email_returns_the_password_hash(
        self, session: AsyncSession, manager: User
    ) -> None:
        """The credential is needed to verify a sign-in.

        Notes:
            This is the one read that carries the hash. Everything above the
            service layer works from ``to_public_dict``.
        """
        repository = UserRepository(session)
        await repository.create(manager)
        found = await repository.get_by_email("claire.bernard@example.com")
        assert found is not None
        assert found.hashed_password == "$2b$12$notarealhash"

    async def test_get_by_email_returns_none_when_unregistered(
        self, session: AsyncSession
    ) -> None:
        """An unknown address reads as None, not as an error."""
        assert await UserRepository(session).get_by_email("no@one.com") is None

    async def test_the_email_is_unique(
        self, session: AsyncSession, manager: User
    ) -> None:
        """Two accounts cannot share a sign-in address."""
        repository = UserRepository(session)
        await repository.create(manager)
        with pytest.raises(IntegrityError):
            await repository.create(
                User(
                    email="claire.bernard@example.com",
                    full_name="Impostor",
                    role=UserRole.MANAGER,
                )
            )

    async def test_uniqueness_is_not_defeated_by_capitalisation(
        self, session: AsyncSession, manager: User
    ) -> None:
        """The model lower-cases the address before it reaches the index."""
        repository = UserRepository(session)
        await repository.create(manager)
        with pytest.raises(IntegrityError):
            await repository.create(
                User(
                    email="Claire.Bernard@Example.COM",
                    full_name="Impostor",
                    role=UserRole.MANAGER,
                )
            )

    # ------------------------------------------------------------------ #
    #  The link to an assistant record
    # ------------------------------------------------------------------ #

    async def test_an_assistant_account_links_to_its_record(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """The link is what makes the row-level planning check possible."""
        stored_hca = await HcaRepository(session).create(hca)
        stored_user = await UserRepository(session).create(
            User(
                email="luc.martin@example.com",
                full_name="Luc Martin",
                role=UserRole.HCA,
                hca_id=stored_hca.id,
            )
        )
        assert stored_user.hca_id == stored_hca.id
        assert stored_user.owns_hca(stored_hca.id) is True
        assert stored_user.owns_hca("another-hca") is False

    async def test_an_assistant_cannot_be_deleted_while_an_account_points_at_it(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """A restricted delete refuses rather than leaving a dangling link.

        Notes:
            An account whose assistant record vanished could not resolve its
            own planning, so the database refuses the delete outright.
        """
        hca_repository = HcaRepository(session)
        stored_hca = await hca_repository.create(hca)
        await UserRepository(session).create(
            User(
                email="luc.martin@example.com",
                full_name="Luc Martin",
                role=UserRole.HCA,
                hca_id=stored_hca.id,
            )
        )
        with pytest.raises(IntegrityError):
            await hca_repository.delete(stored_hca.id)

    # ------------------------------------------------------------------ #
    #  set_role — the promote path
    # ------------------------------------------------------------------ #

    async def test_set_role_promotes_to_manager(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """An admin promotes an account by changing only its role."""
        stored_hca = await HcaRepository(session).create(hca)
        repository = UserRepository(session)
        stored = await repository.create(
            User(
                email="luc.martin@example.com",
                full_name="Luc Martin",
                role=UserRole.HCA,
                hca_id=stored_hca.id,
            )
        )
        promoted = await repository.set_role(stored.id, UserRole.MANAGER)
        assert promoted is not None
        assert promoted.role is UserRole.MANAGER
        assert promoted.is_manager() is True

    async def test_set_role_leaves_the_rest_untouched(
        self, session: AsyncSession, manager: User
    ) -> None:
        """A promotion is not a side effect of saving an unrelated edit."""
        repository = UserRepository(session)
        stored = await repository.create(manager)
        promoted = await repository.set_role(stored.id, UserRole.ADMIN)
        assert promoted is not None
        assert promoted.full_name == "Claire Bernard"
        assert promoted.hashed_password == "$2b$12$notarealhash"

    async def test_set_role_of_an_unknown_account_returns_none(
        self, session: AsyncSession
    ) -> None:
        """Promoting an absent account reports rather than raising."""
        repository = UserRepository(session)
        assert await repository.set_role("no-such-id", UserRole.MANAGER) is None

    # ------------------------------------------------------------------ #
    #  set_active
    # ------------------------------------------------------------------ #

    async def test_set_active_disables_sign_in(
        self, session: AsyncSession, manager: User
    ) -> None:
        """A deactivated account keeps its data but cannot sign in."""
        repository = UserRepository(session)
        stored = await repository.create(manager)
        disabled = await repository.set_active(stored.id, False)
        assert disabled is not None
        assert disabled.is_active is False

    # ------------------------------------------------------------------ #
    #  Update
    # ------------------------------------------------------------------ #

    async def test_update_keeps_the_hash_when_none_is_supplied(
        self, session: AsyncSession, manager: User
    ) -> None:
        """An update built from a public view must not lock the account out.

        Notes:
            A public view carries ``hashed_password = None``; copying that
            through would erase the credential.
        """
        repository = UserRepository(session)
        stored = await repository.create(manager)
        edited = stored.model_copy(
            update={"full_name": "Claire B.", "hashed_password": None}
        )
        updated = await repository.update(edited)
        assert updated is not None
        assert updated.full_name == "Claire B."
        assert updated.hashed_password == "$2b$12$notarealhash"

    async def test_update_replaces_the_hash_when_one_is_supplied(
        self, session: AsyncSession, manager: User
    ) -> None:
        """A password change does write the new hash."""
        repository = UserRepository(session)
        stored = await repository.create(manager)
        rotated = await repository.update(
            stored.model_copy(update={"hashed_password": "$2b$12$rotated"})
        )
        assert rotated is not None
        assert rotated.hashed_password == "$2b$12$rotated"

    # ------------------------------------------------------------------ #
    #  Listing and counting
    # ------------------------------------------------------------------ #

    async def test_the_role_filter_restricts_the_page(
        self, session: AsyncSession, manager: User
    ) -> None:
        """Filtering by role returns only that role."""
        repository = UserRepository(session)
        await repository.create(manager)
        await repository.create(
            User(
                email="root@example.com",
                full_name="Root",
                role=UserRole.ADMIN,
            )
        )
        admins = await repository.list(role=UserRole.ADMIN)
        assert [entry.email for entry in admins] == ["root@example.com"]

    async def test_count_admins(self, session: AsyncSession, manager: User) -> None:
        """The admin count guards against removing the last one.

        Notes:
            With no admin left, nobody could run a planning or promote a
            manager.
        """
        repository = UserRepository(session)
        await repository.create(manager)
        assert await repository.count_admins() == 0
        await repository.create(
            User(email="root@example.com", full_name="Root", role=UserRole.ADMIN)
        )
        assert await repository.count_admins() == 1

    # ------------------------------------------------------------------ #
    #  Delete
    # ------------------------------------------------------------------ #

    async def test_delete_removes_the_account(
        self, session: AsyncSession, manager: User
    ) -> None:
        """A deleted account no longer reads back."""
        repository = UserRepository(session)
        stored = await repository.create(manager)
        assert await repository.delete(stored.id) is True
        assert await repository.get(stored.id) is None

    async def test_delete_of_an_unknown_account_reports_false(
        self, session: AsyncSession
    ) -> None:
        """Deleting an absent account is a no-op."""
        assert await UserRepository(session).delete("no-such-id") is False
