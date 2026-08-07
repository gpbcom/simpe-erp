from __future__ import annotations

# Standard library imports
from typing import Optional

# Third-party imports
from pydantic import BaseModel, EmailStr, Field, field_validator

# First-party imports
from models.schemas.exceptions import (
    MTLoginRequestInvalidEmail,
    MTLoginRequestInvalidPassword,
)


class LoginRequest(BaseModel):
    """The payload signing in to an existing account.

    Attributes:
        email (EmailStr): The sign-in address.
        password (str): The plaintext password.

    Notes:
        No length rule is applied to the password here, unlike on
        registration. A rule would reject a sign-in attempt before it reached
        the credential check, which tells the caller that the stored password
        does not have that shape — and would lock out any account created
        before the rule was tightened.
    """

    email: EmailStr = Field(description="The sign-in address.")
    password: str = Field(description="The plaintext password.")

    @field_validator("email", mode="before")
    def validate_email(cls, value: Optional[str]) -> str:
        """Validates that ``email`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``email`` value.

        Returns:
            str: The stripped, lower-cased address.

        Raises:
            MTLoginRequestInvalidEmail: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTLoginRequestInvalidEmail(
                f"Invalid email: {value!r}. Must be a non-empty string."
            )
        return value.strip().lower()

    @field_validator("password", mode="before")
    def validate_password(cls, value: Optional[str]) -> str:
        """Validates that ``password`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``password`` value.

        Returns:
            str: The password, unmodified.

        Raises:
            MTLoginRequestInvalidPassword: If ``value`` is not a non-empty
                string.

        Notes:
            The value never appears in the error message, which would put a
            credential into the logs.
        """
        if not isinstance(value, str) or not value:
            raise MTLoginRequestInvalidPassword(
                "Invalid password. Must be a non-empty string."
            )
        return value
