from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from typing import Any, Dict

# Third-party imports
from pydantic import ValidationError
import pytest

# First-party imports
from models.auth.exceptions import (
    MTInvalidUserException,
    MTUserInvalidDate,
    MTUserInvalidEmail,
    MTUserInvalidFullName,
    MTUserInvalidHashedPassword,
    MTUserInvalidHcaId,
    MTUserInvalidId,
    MTUserInvalidRole,
    MTUserRoleHcaRequiresHcaId,
)
from models.auth.user import User
from models.enums import UserRole


@pytest.fixture
def valid_manager_kwargs() -> Dict[str, Any]:
    """Return the keyword arguments for a valid manager account.

    Returns:
        Dict[str, Any]: Constructor keyword arguments.
    """
    return {
        "email": "manager@example.com",
        "full_name": "Claire Bernard",
        "role": UserRole.MANAGER,
        "company_id": "company-1",
        "hashed_password": "$2b$12$abcdefghijklmnopqrstuv",
    }


class TestUser:
    """Tests for the User model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_minimal_valid_construction(
        self, valid_manager_kwargs: Dict[str, Any]
    ) -> None:
        """An account is an address, a display name and a role."""
        user = User(**valid_manager_kwargs)
        assert user.email == "manager@example.com"
        assert user.role is UserRole.MANAGER
        assert user.is_active is True

    def test_an_hca_account_needs_an_hca_id(self) -> None:
        """An assistant account is linked to its assistant record."""
        user = User(
            company_id="company-1",
            email="luc@example.com",
            full_name="Luc Martin",
            role=UserRole.HCA,
            hca_id="hca-1",
        )
        assert user.hca_id == "hca-1"

    def test_a_password_is_optional(self) -> None:
        """An account can exist before a password is set."""
        user = User(
            company_id="company-1",
            email="a@b.com",
            full_name="A B",
            role=UserRole.MANAGER,
        )
        assert user.hashed_password is None

    # ------------------------------------------------------------------ #
    #  email validation
    # ------------------------------------------------------------------ #

    def test_the_email_is_lower_cased(self) -> None:
        """Sign-in is case-insensitive.

        Notes:
            Lower-casing is also what stops the uniqueness index being defeated
            by changing capitalisation.
        """
        user = User(
            company_id="company-1",
            email="  Manager@Example.COM  ",
            full_name="Claire",
            role=UserRole.MANAGER,
        )
        assert user.email == "manager@example.com"

    @pytest.mark.parametrize(
        "invalid_email",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(42, id="Invalid - int"),
        ],
    )
    def test_a_missing_email_raises_the_model_exception(
        self, valid_manager_kwargs: Dict[str, Any], invalid_email: Any
    ) -> None:
        """A missing address raises the model's own exception."""
        with pytest.raises(MTUserInvalidEmail):
            User(**{**valid_manager_kwargs, "email": invalid_email})

    def test_a_malformed_email_is_rejected(
        self, valid_manager_kwargs: Dict[str, Any]
    ) -> None:
        """An address without a domain is rejected."""
        with pytest.raises(ValidationError):
            User(**{**valid_manager_kwargs, "email": "manager"})

    # ------------------------------------------------------------------ #
    #  Other field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        ("field", "invalid_value", "expected_exception"),
        [
            pytest.param("id", "", MTUserInvalidId, id="Invalid - empty id"),
            pytest.param("id", 7, MTUserInvalidId, id="Invalid - int id"),
            pytest.param(
                "full_name", "", MTUserInvalidFullName, id="Invalid - empty name"
            ),
            pytest.param(
                "full_name", None, MTUserInvalidFullName, id="Invalid - None name"
            ),
            pytest.param(
                "hashed_password",
                "",
                MTUserInvalidHashedPassword,
                id="Invalid - empty hash",
            ),
            pytest.param(
                "hashed_password",
                1,
                MTUserInvalidHashedPassword,
                id="Invalid - int hash",
            ),
            pytest.param(
                "role", "superuser", MTUserInvalidRole, id="Invalid - unknown role"
            ),
            pytest.param(
                "role", "ADMIN", MTUserInvalidRole, id="Invalid - wrong case role"
            ),
            pytest.param("hca_id", "", MTUserInvalidHcaId, id="Invalid - empty hca_id"),
            pytest.param(
                "created_at",
                1234567890,
                MTUserInvalidDate,
                id="Invalid - int timestamp",
            ),
        ],
    )
    def test_invalid_fields_raise(
        self,
        valid_manager_kwargs: Dict[str, Any],
        field: str,
        invalid_value: Any,
        expected_exception: type,
    ) -> None:
        """Each field rejects its own invalid values with its own exception."""
        with pytest.raises(expected_exception):
            User(**{**valid_manager_kwargs, field: invalid_value})

    def test_a_none_role_defaults_to_the_least_privileged(self) -> None:
        """A missing role never fails open into a manager or admin account."""
        user = User(
            company_id="company-1",
            email="a@b.com",
            full_name="A B",
            role=None,
            hca_id="hca-1",
        )
        assert user.role is UserRole.HCA

    def test_the_password_hash_is_not_stripped(self) -> None:
        """A hash is opaque; trimming it would corrupt the credential."""
        user = User(
            company_id="company-1",
            email="a@b.com",
            full_name="A B",
            role=UserRole.MANAGER,
            hashed_password="  $2b$12$abc  ",
        )
        assert user.hashed_password == "  $2b$12$abc  "

    # ------------------------------------------------------------------ #
    #  Cross-field validation
    # ------------------------------------------------------------------ #

    def test_an_hca_account_without_a_link_raises(self) -> None:
        """An assistant account with no hca_id cannot be built.

        Notes:
            Without the link there is nothing to compare a planning request
            against, so the account could read no planning at all — or a naive
            check could read it as unrestricted. Refusing to build it removes
            the state entirely.
        """
        with pytest.raises(MTUserRoleHcaRequiresHcaId):
            User(
                company_id="company-1",
                email="luc@example.com",
                full_name="Luc Martin",
                role=UserRole.HCA,
            )

    @pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.ADMIN])
    def test_non_hca_accounts_need_no_link(self, role: UserRole) -> None:
        """Only assistant accounts require an assistant record."""
        user = User(company_id="company-1", email="a@b.com", full_name="A B", role=role)
        assert user.hca_id is None

    # ------------------------------------------------------------------ #
    #  Role helpers
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        ("role", "expected"),
        [
            pytest.param(UserRole.HCA, False, id="hca is not a manager"),
            pytest.param(UserRole.MANAGER, True, id="manager is a manager"),
            pytest.param(UserRole.ADMIN, True, id="admin outranks manager"),
        ],
    )
    def test_is_manager(self, role: UserRole, expected: bool) -> None:
        """Manager privileges are held by managers and admins."""
        user = User(
            company_id="company-1",
            email="a@b.com",
            full_name="A B",
            role=role,
            hca_id="hca-1" if role is UserRole.HCA else None,
        )
        assert user.is_manager() is expected

    @pytest.mark.parametrize(
        ("role", "expected"),
        [
            pytest.param(UserRole.HCA, False, id="hca is not an admin"),
            pytest.param(UserRole.MANAGER, False, id="manager is not an admin"),
            pytest.param(UserRole.ADMIN, True, id="admin is an admin"),
        ],
    )
    def test_is_admin(self, role: UserRole, expected: bool) -> None:
        """Only the admin role is an administrator."""
        user = User(
            company_id="company-1",
            email="a@b.com",
            full_name="A B",
            role=role,
            hca_id="hca-1" if role is UserRole.HCA else None,
        )
        assert user.is_admin() is expected

    # ------------------------------------------------------------------ #
    #  owns_hca — the row-level planning rule
    # ------------------------------------------------------------------ #

    def test_an_assistant_owns_their_own_planning(self) -> None:
        """An assistant may read the planning of their own record."""
        user = User(
            company_id="company-1",
            email="luc@example.com",
            full_name="Luc",
            role=UserRole.HCA,
            hca_id="hca-1",
        )
        assert user.owns_hca("hca-1") is True

    def test_an_assistant_does_not_own_another_planning(self) -> None:
        """An assistant may not read another assistant's planning.

        Notes:
            This is the rule a route guard cannot express: the guard only
            proves the caller is *an* assistant, not the right one.
        """
        user = User(
            company_id="company-1",
            email="luc@example.com",
            full_name="Luc",
            role=UserRole.HCA,
            hca_id="hca-1",
        )
        assert user.owns_hca("hca-2") is False

    @pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.ADMIN])
    def test_managers_and_admins_see_every_planning(self, role: UserRole) -> None:
        """Managers and admins are not restricted to one assistant."""
        user = User(company_id="company-1", email="a@b.com", full_name="A B", role=role)
        assert user.owns_hca("hca-1") is True
        assert user.owns_hca("hca-2") is True

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTUserInvalidDate,
            MTUserInvalidEmail,
            MTUserInvalidFullName,
            MTUserInvalidHashedPassword,
            MTUserInvalidHcaId,
            MTUserInvalidId,
            MTUserInvalidRole,
            MTUserRoleHcaRequiresHcaId,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidUserException."""
        assert issubclass(exception_class, MTInvalidUserException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_to_public_dict_excludes_the_password_hash(
        self, valid_manager_kwargs: Dict[str, Any]
    ) -> None:
        """The credential never leaves the backend.

        Notes:
            Excluded here rather than at each call site, so a new endpoint
            cannot leak it by forgetting to.
        """
        public = User(**valid_manager_kwargs).to_public_dict()
        assert "hashed_password" not in public
        assert public["email"] == "manager@example.com"

    def test_to_public_dict_is_json_serializable(
        self, valid_manager_kwargs: Dict[str, Any]
    ) -> None:
        """The public view survives a JSON round-trip."""
        # Standard library imports
        import json

        user = User(
            **{
                **valid_manager_kwargs,
                "created_at": datetime(2026, 8, 5, tzinfo=UTC),
            }
        )
        assert json.loads(json.dumps(user.to_public_dict()))["role"] == "manager"

    def test_timestamps_serialize_to_iso_strings(
        self, valid_manager_kwargs: Dict[str, Any]
    ) -> None:
        """Timestamps leave the model as ISO-8601 text."""
        user = User(
            **{
                **valid_manager_kwargs,
                "updated_at": datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
            }
        )
        assert user.model_dump()["updated_at"] == "2026-08-05T12:00:00+00:00"

    def test_model_dump_round_trip(self, valid_manager_kwargs: Dict[str, Any]) -> None:
        """An account survives a dump-and-rebuild unchanged."""
        user = User(**valid_manager_kwargs)
        assert User(**user.model_dump()) == user
