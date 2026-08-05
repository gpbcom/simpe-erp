from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.auth.exceptions import (
    MTAccessTokenInvalidAccessToken,
    MTAccessTokenInvalidExpiresIn,
    MTAccessTokenInvalidTokenType,
)


class AccessToken(BaseModel):
    """A bearer token issued on a successful sign-in.

    Attributes:
        BEARER_TOKEN_TYPE (ClassVar[str]): The only token type issued.
        access_token (str): The signed JWT.
        token_type (str): Always ``"bearer"``.
        expires_in (int): Lifetime in seconds from issuance.

    Notes:
        The field names follow the OAuth 2.0 token-response shape, so the
        standard client-side handling applies unchanged.
    """

    BEARER_TOKEN_TYPE: ClassVar[str] = "bearer"

    access_token: str = Field(description="The signed JWT.")
    token_type: str = Field(
        default=BEARER_TOKEN_TYPE,
        description='Always "bearer".',
    )
    expires_in: int = Field(description="Lifetime in seconds from issuance.")

    @field_validator("access_token", mode="before")
    def validate_access_token(cls, value: Optional[str]) -> str:
        """Validates that ``access_token`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``access_token`` value.

        Returns:
            str: The token, unmodified.

        Raises:
            MTAccessTokenInvalidAccessToken: If ``value`` is not a non-empty
                string.

        Notes:
            The token is not stripped: it is an opaque signed value, and
            altering it would invalidate the signature rather than fix it.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTAccessTokenInvalidAccessToken(
                "Invalid access_token. Must be a non-empty string."
            )
        return value

    @field_validator("token_type", mode="before")
    def validate_token_type(cls, value: Optional[str]) -> str:
        """Validates that ``token_type`` is the bearer type.

        Args:
            value (Optional[str]): Raw ``token_type`` value. ``None`` falls
                back to :attr:`BEARER_TOKEN_TYPE`.

        Returns:
            str: The lower-cased token type.

        Raises:
            MTAccessTokenInvalidTokenType: If ``value`` is anything other than
                ``"bearer"``.
        """
        if value is None:
            return cls.BEARER_TOKEN_TYPE
        if not isinstance(value, str) or value.strip().lower() != (
            cls.BEARER_TOKEN_TYPE
        ):
            raise MTAccessTokenInvalidTokenType(
                f"Invalid token_type: {value!r}. Must be {cls.BEARER_TOKEN_TYPE!r}."
            )
        return cls.BEARER_TOKEN_TYPE

    @field_validator("expires_in", mode="before")
    def validate_expires_in(cls, value: Union[int, str, None]) -> int:
        """Validates that ``expires_in`` is a strictly positive integer.

        Args:
            value (Union[int, str, None]): Raw ``expires_in`` value, in seconds.

        Returns:
            int: The validated lifetime.

        Raises:
            MTAccessTokenInvalidExpiresIn: If ``value`` is not a strictly
                positive integer.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTAccessTokenInvalidExpiresIn(
                f"Invalid expires_in: {value!r}. "
                f"Must be a strictly positive integer number of seconds."
            )
        if value <= 0:
            raise MTAccessTokenInvalidExpiresIn(
                f"Invalid expires_in: {value!r}. Must be strictly positive."
            )
        return value
