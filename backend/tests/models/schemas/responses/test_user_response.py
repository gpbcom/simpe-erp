from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
import json
from typing import Any, Dict

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.enums import AccountOrigin, UserRole
from models.schemas.exceptions import (
    MTInvalidUserResponseException,
    MTUserResponseInvalidDate,
    MTUserResponseInvalidEmail,
    MTUserResponseInvalidFullName,
    MTUserResponseInvalidHcaId,
    MTUserResponseInvalidId,
    MTUserResponseInvalidIsActive,
    MTUserResponseInvalidRole,
)
from models.schemas.responses.user_response import UserResponse


@pytest.fixture
def valid_response_kwargs() -> Dict[str, Any]:
    """Return the minimal keyword arguments for a valid response.

    Returns:
        Dict[str, Any]: Constructor keyword arguments.
    """
    return {
        "id": "user-1",
        "email": "manager@example.com",
        "full_name": "Manager Account",
        "role": UserRole.MANAGER,
        "is_active": True,
    }


class TestUserResponse:
    """Tests for the UserResponse schema."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_minimal_valid_construction(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """An account publishes its identity, role and state."""
        response = UserResponse(**valid_response_kwargs)
        assert response.id == "user-1"
        assert response.role is UserRole.MANAGER
        assert response.is_active is True

    def test_optional_fields_default_to_unset(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """An unlinked account carries no assistant and no timestamps."""
        response = UserResponse(**valid_response_kwargs)
        assert response.hca_id is None
        assert response.created_at is None
        assert response.updated_at is None

    def test_the_address_is_lower_cased(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """The published address matches the stored one, which is lower-cased."""
        response = UserResponse(
            **{**valid_response_kwargs, "email": "  Manager@Example.COM "}
        )
        assert response.email == "manager@example.com"

    # ------------------------------------------------------------------ #
    #  The password hash cannot be published
    # ------------------------------------------------------------------ #

    def test_there_is_no_password_hash_field(self) -> None:
        """The credential is absent by construction, not by exclusion.

        Notes:
            This is the property the whole schema exists for. A dump that
            excluded the hash by name could stop excluding it; a field that was
            never declared cannot be published at all.
        """
        assert "hashed_password" not in UserResponse.model_fields

    def test_a_supplied_password_hash_is_dropped(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """An extra field on the payload does not survive into the response."""
        response = UserResponse(
            **{**valid_response_kwargs, "hashed_password": "$2b$12$hash"}
        )
        assert "hashed_password" not in response.model_dump()

    def test_from_user_never_carries_the_hash(self) -> None:
        """Building from a stored account leaves the credential behind."""
        user = User(
            id="user-1",
            email="manager@example.com",
            full_name="Manager Account",
            hashed_password="$2b$12$abcdefghijklmnopqrstuv",
            role=UserRole.MANAGER,
        )
        dumped = json.dumps(UserResponse.from_user(user).model_dump(mode="json"))
        assert "hashed_password" not in dumped
        assert "$2b$" not in dumped

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(42, id="Invalid - int"),
        ],
    )
    def test_invalid_id_raises(
        self, valid_response_kwargs: Dict[str, Any], invalid_value: Any
    ) -> None:
        """An identifier that is neither None nor a real string is rejected."""
        with pytest.raises(MTUserResponseInvalidId):
            UserResponse(**{**valid_response_kwargs, "id": invalid_value})

    def test_a_none_id_is_accepted(self, valid_response_kwargs: Dict[str, Any]) -> None:
        """An account that has not been stored yet has no identifier."""
        assert UserResponse(**{**valid_response_kwargs, "id": None}).id is None

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(42, id="Invalid - int"),
        ],
    )
    def test_invalid_email_raises(
        self, valid_response_kwargs: Dict[str, Any], invalid_value: Any
    ) -> None:
        """An address that is not a non-empty string is rejected."""
        with pytest.raises(MTUserResponseInvalidEmail):
            UserResponse(**{**valid_response_kwargs, "email": invalid_value})

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("  ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_invalid_full_name_raises(
        self, valid_response_kwargs: Dict[str, Any], invalid_value: Any
    ) -> None:
        """A display name that is not a non-empty string is rejected."""
        with pytest.raises(MTUserResponseInvalidFullName):
            UserResponse(**{**valid_response_kwargs, "full_name": invalid_value})

    def test_an_unknown_role_raises(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """A role the stack does not know is rejected rather than published."""
        with pytest.raises(MTUserResponseInvalidRole):
            UserResponse(**{**valid_response_kwargs, "role": "superuser"})

    def test_a_role_string_is_coerced(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """A stored role value rebuilds into its enum."""
        response = UserResponse(**{**valid_response_kwargs, "role": "admin"})
        assert response.role is UserRole.ADMIN

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param(1, id="Invalid - int"),
            pytest.param("true", id="Invalid - string"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_invalid_is_active_raises(
        self, valid_response_kwargs: Dict[str, Any], invalid_value: Any
    ) -> None:
        """A truthy value is not a boolean.

        Notes:
            A client reads this field to decide whether to show an account as
            suspended; coercing ``"false"`` to ``True`` would flip that.
        """
        with pytest.raises(MTUserResponseInvalidIsActive):
            UserResponse(**{**valid_response_kwargs, "is_active": invalid_value})

    def test_an_invalid_hca_id_raises(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """An assistant link that is not a real identifier is rejected."""
        with pytest.raises(MTUserResponseInvalidHcaId):
            UserResponse(**{**valid_response_kwargs, "hca_id": "   "})

    def test_an_unparseable_timestamp_raises(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """A timestamp that is not ISO-8601 is rejected."""
        with pytest.raises(MTUserResponseInvalidDate):
            UserResponse(**{**valid_response_kwargs, "created_at": "last tuesday"})

    def test_an_iso_timestamp_is_parsed(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """A stored ISO-8601 string rebuilds into a datetime."""
        response = UserResponse(
            **{**valid_response_kwargs, "created_at": "2026-08-05T12:00:00+00:00"}
        )
        assert response.created_at == datetime(2026, 8, 5, 12, 0, tzinfo=UTC)

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTUserResponseInvalidDate,
            MTUserResponseInvalidEmail,
            MTUserResponseInvalidFullName,
            MTUserResponseInvalidHcaId,
            MTUserResponseInvalidId,
            MTUserResponseInvalidIsActive,
            MTUserResponseInvalidRole,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidUserResponseException."""
        assert issubclass(exception_class, MTInvalidUserResponseException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_timestamps_serialize_to_iso_8601(
        self, valid_response_kwargs: Dict[str, Any]
    ) -> None:
        """A client reads a string, not a Python datetime."""
        response = UserResponse(
            **{
                **valid_response_kwargs,
                "updated_at": datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
            }
        )
        assert response.model_dump()["updated_at"] == "2026-08-05T12:00:00+00:00"

    def test_from_user_publishes_every_public_field(self) -> None:
        """The published shape carries the whole account bar its credential."""
        user = User(
            id="user-1",
            email="hca@example.com",
            full_name="Assistant Account",
            hashed_password="$2b$12$abcdefghijklmnopqrstuv",
            role=UserRole.HCA,
            hca_id="hca-1",
            created_at=datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 5, 13, 0, tzinfo=UTC),
        )
        published = UserResponse.from_user(user).model_dump(mode="json")
        assert published == {
            "id": "user-1",
            "email": "hca@example.com",
            "full_name": "Assistant Account",
            "role": "hca",
            "is_active": True,
            "hca_id": "hca-1",
            "company_id": None,
            "must_change_password": False,
            "created_at": "2026-08-05T12:00:00+00:00",
            "updated_at": "2026-08-05T13:00:00+00:00",
        }

    def test_from_user_publishes_the_temporary_password_flag(self) -> None:
        """A client must be able to see that a password change is owed.

        Notes:
            The middleware answers 403 on every route but the password change
            while this flag is set. Without it on the wire, a client can only
            discover the state by sending a request it knows will be refused
            and then reading the error body — so the sign-in screen cannot go
            straight to the change form.
        """
        user = User(
            id="user-2",
            email="manager@example.com",
            full_name="Manager Account",
            hashed_password="$2b$12$abcdefghijklmnopqrstuv",
            role=UserRole.MANAGER,
            company_id="company-1",
            account_origin=AccountOrigin.CREATED_BY_STAFF,
            must_change_password=True,
        )

        published = UserResponse.from_user(user)

        assert published.must_change_password is True
        assert published.company_id == "company-1"

    def test_a_non_boolean_temporary_password_flag_is_refused(self) -> None:
        """A truthy string must not be coerced into the flag."""
        with pytest.raises(MTUserResponseInvalidIsActive):
            UserResponse(
                email="hca@example.com",
                full_name="Assistant Account",
                role=UserRole.HCA,
                is_active=True,
                must_change_password="yes",
            )
