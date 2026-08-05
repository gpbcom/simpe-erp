from __future__ import annotations

# Standard library imports
import os
from typing import ClassVar, FrozenSet, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.configuration.exceptions import (
    MTAuthConfigInvalidJwtAlgorithm,
    MTAuthConfigInvalidJwtSecretEnv,
    MTAuthConfigInvalidTokenExpiry,
    MTAuthConfigMissingSecret,
)


class AuthConfig(BaseModel):
    """Settings governing authentication and access-token issuance.

    Attributes:
        SUPPORTED_JWT_ALGORITHMS (ClassVar[FrozenSet[str]]): The signing
            algorithms accepted for the access token.
        MAX_EXPIRE_MINUTES (ClassVar[int]): Longest token lifetime accepted,
            one year expressed in minutes.
        jwt_secret_env (str): Name of the environment variable holding the JWT
            signing secret.
        jwt_algorithm (str): Signing algorithm. Defaults to ``"HS256"``.
        access_token_expire_minutes (int): Access-token lifetime in minutes.

    Notes:
        Only symmetric HMAC algorithms are accepted. Allowing an asymmetric
        algorithm alongside a shared secret is how the ``alg`` confusion attack
        gets in, and this service has no need for one.
    """

    SUPPORTED_JWT_ALGORITHMS: ClassVar[FrozenSet[str]] = frozenset(
        {"HS256", "HS384", "HS512"}
    )
    MAX_EXPIRE_MINUTES: ClassVar[int] = 365 * 24 * 60

    jwt_secret_env: str = Field(
        default="JWT_SECRET_KEY",
        description="Name of the environment variable holding the JWT secret.",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm.",
    )
    access_token_expire_minutes: int = Field(
        default=60 * 12,
        description="Access-token lifetime, in minutes.",
    )

    @field_validator("jwt_secret_env", mode="before")
    def validate_jwt_secret_env(cls, value: Optional[str]) -> str:
        """Validates that ``jwt_secret_env`` names an environment variable.

        Args:
            value (Optional[str]): Raw ``jwt_secret_env`` value.

        Returns:
            str: The stripped environment-variable name.

        Raises:
            MTAuthConfigInvalidJwtSecretEnv: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTAuthConfigInvalidJwtSecretEnv(
                f"Invalid jwt_secret_env: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("jwt_algorithm", mode="before")
    def validate_jwt_algorithm(cls, value: Optional[str]) -> str:
        """Validates that ``jwt_algorithm`` is a supported HMAC algorithm.

        Args:
            value (Optional[str]): Raw ``jwt_algorithm`` value.

        Returns:
            str: The validated algorithm name.

        Raises:
            MTAuthConfigInvalidJwtAlgorithm: If ``value`` is not one of
                :attr:`SUPPORTED_JWT_ALGORITHMS`.
        """
        if not isinstance(value, str) or value.strip() not in (
            cls.SUPPORTED_JWT_ALGORITHMS
        ):
            raise MTAuthConfigInvalidJwtAlgorithm(
                f"Invalid jwt_algorithm: {value!r}. Must be one of: "
                f"{', '.join(sorted(cls.SUPPORTED_JWT_ALGORITHMS))}."
            )
        return value.strip()

    @field_validator("access_token_expire_minutes", mode="before")
    def validate_access_token_expire_minutes(cls, value: Union[int, str]) -> int:  # noqa: E501
        """Validates that ``access_token_expire_minutes`` is a sane lifetime.

        Args:
            value (Union[int, str]): Raw lifetime value, in minutes.

        Returns:
            int: The validated lifetime.

        Raises:
            MTAuthConfigInvalidTokenExpiry: If ``value`` is not an integer
                within ``1..MAX_EXPIRE_MINUTES``.

        Notes:
            The upper bound exists so a mistyped configuration cannot mint a
            token that effectively never expires.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTAuthConfigInvalidTokenExpiry(
                f"Invalid access_token_expire_minutes: {value!r}. "
                f"Must be an integer within 1..{cls.MAX_EXPIRE_MINUTES}."
            )
        if not 1 <= value <= cls.MAX_EXPIRE_MINUTES:
            raise MTAuthConfigInvalidTokenExpiry(
                f"Invalid access_token_expire_minutes: {value!r}. "
                f"Must be within 1..{cls.MAX_EXPIRE_MINUTES}."
            )
        return value

    ############################
    # Publicly Exposed Methods #
    ############################
    def get_jwt_secret(self) -> str:
        """Return the JWT signing secret from the environment.

        Returns:
            str: The resolved secret.

        Raises:
            MTAuthConfigMissingSecret: If the environment variable named by
                ``jwt_secret_env`` is unset or empty.

        Notes:
            There is deliberately no default secret. A fallback value would let
            the service boot in production with a signing key that is public
            knowledge, which is worse than refusing to start.
        """
        secret = os.environ.get(self.jwt_secret_env, "")
        if not secret:
            raise MTAuthConfigMissingSecret(
                f"Environment variable {self.jwt_secret_env!r} is not set. "
                f"It must hold the JWT signing secret."
            )
        return secret
