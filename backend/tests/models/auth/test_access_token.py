from __future__ import annotations

# Standard library imports

# Third-party imports
import pytest

# First-party imports
from models.auth.access_token import AccessToken
from models.auth.exceptions import (
    MTAccessTokenInvalidAccessToken,
    MTAccessTokenInvalidExpiresIn,
    MTAccessTokenInvalidTokenType,
    MTInvalidAccessTokenException,
)
from tests.annotations import ModelInput


class TestAccessToken:
    """Tests for the AccessToken model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_minimal_valid_construction(self) -> None:
        """A token response is the token and its lifetime."""
        token = AccessToken(access_token="header.payload.signature", expires_in=3600)
        assert token.access_token == "header.payload.signature"
        assert token.expires_in == 3600

    def test_token_type_defaults_to_bearer(self) -> None:
        """The only token type issued is bearer."""
        token = AccessToken(access_token="abc", expires_in=60)
        assert token.token_type == "bearer"

    def test_a_none_token_type_defaults_to_bearer(self) -> None:
        """An explicit None yields the default rather than an error."""
        token = AccessToken(access_token="abc", expires_in=60, token_type=None)
        assert token.token_type == "bearer"

    def test_the_token_type_is_lower_cased(self) -> None:
        """A capitalised bearer type is normalised."""
        token = AccessToken(access_token="abc", expires_in=60, token_type="Bearer")
        assert token.token_type == "bearer"

    # ------------------------------------------------------------------ #
    #  access_token validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_token",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(12345, id="Invalid - int"),
        ],
    )
    def test_invalid_access_token_raises(self, invalid_token: ModelInput) -> None:
        """A token that is not a non-empty string is rejected."""
        with pytest.raises(MTAccessTokenInvalidAccessToken):
            AccessToken(access_token=invalid_token, expires_in=60)

    def test_the_token_is_not_stripped(self) -> None:
        """A signed value is opaque; altering it would break the signature."""
        token = AccessToken(access_token=" abc ", expires_in=60)
        assert token.access_token == " abc "

    def test_the_error_message_does_not_echo_the_token(self) -> None:
        """A rejected token is not repeated back into the message.

        Notes:
            Error strings reach logs; echoing a credential-shaped value there
            is how one leaks.
        """
        with pytest.raises(MTAccessTokenInvalidAccessToken) as raised:
            AccessToken(access_token="   ", expires_in=60)
        assert "   " not in str(raised.value).replace("Must be a non-empty string.", "")

    # ------------------------------------------------------------------ #
    #  token_type validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_type",
        [
            pytest.param("basic", id="Invalid - basic"),
            pytest.param("mac", id="Invalid - mac"),
            pytest.param("", id="Invalid - empty"),
            pytest.param(1, id="Invalid - int"),
        ],
    )
    def test_invalid_token_type_raises(self, invalid_type: ModelInput) -> None:
        """Anything other than bearer is rejected."""
        with pytest.raises(MTAccessTokenInvalidTokenType):
            AccessToken(access_token="abc", expires_in=60, token_type=invalid_type)

    # ------------------------------------------------------------------ #
    #  expires_in validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_expiry",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(-1, id="Invalid - negative"),
            pytest.param("3600", id="Invalid - string"),
            pytest.param(3600.0, id="Invalid - float"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(True, id="Invalid - bool"),
        ],
    )
    def test_invalid_expires_in_raises(self, invalid_expiry: ModelInput) -> None:
        """A lifetime that is not a strictly positive integer is rejected."""
        with pytest.raises(MTAccessTokenInvalidExpiresIn):
            AccessToken(access_token="abc", expires_in=invalid_expiry)

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTAccessTokenInvalidAccessToken,
            MTAccessTokenInvalidExpiresIn,
            MTAccessTokenInvalidTokenType,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidAccessTokenException."""
        assert issubclass(exception_class, MTInvalidAccessTokenException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_model_dump_matches_the_oauth_shape(self) -> None:
        """The payload carries the standard OAuth 2.0 field names."""
        token = AccessToken(access_token="abc", expires_in=3600)
        assert token.model_dump() == {
            "access_token": "abc",
            "token_type": "bearer",
            "expires_in": 3600,
        }

    def test_bearer_token_type_is_not_a_field(self) -> None:
        """The ClassVar stays out of the serialised payload."""
        dumped = AccessToken(access_token="abc", expires_in=60).model_dump()
        assert "BEARER_TOKEN_TYPE" not in dumped
