from __future__ import annotations

# Standard library imports
from typing import Optional

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import (
    MTTemporaryCredentialsResponseInvalidEmail,
    MTTemporaryCredentialsResponseInvalidPassword,
)


class TemporaryCredentialsResponse(BaseModel):
    """The one-time credentials handed to an administrator to pass on.

    Attributes:
        user_id (str): The account that was created.
        email (str): The sign-in address.
        temporary_password (str): The generated password, in plain text.
        must_change_password (bool): Always ``True``; stated so the client can
            say so on screen.

    Notes:
        **This is the only place a password is ever returned by this API, and
        it happens exactly once.** The stored form is a hash, so an
        administrator who loses this response regenerates the account's
        password rather than looking it up.

        ``must_change_password`` is echoed rather than assumed, so the screen
        showing these credentials can tell the administrator what to say when
        handing them over: this password works once, to set a real one.

        The value must not be logged by whatever renders it. It is a working
        credential until its holder replaces it.
    """

    user_id: str = Field(description="The account that was created.")
    email: str = Field(description="The sign-in address.")
    temporary_password: str = Field(description="The generated password.")
    must_change_password: bool = Field(
        default=True, description="Whether the holder must replace it first."
    )

    @field_validator("temporary_password", mode="before")
    def validate_temporary_password(cls, value: Optional[str]) -> str:
        """Validates that a password is actually being handed over.

        Args:
            value (Optional[str]): Raw password value.

        Returns:
            str: The password, unmodified.

        Raises:
            MTTemporaryCredentialsResponseInvalidPassword: If ``value`` is not
                a non-empty string.

        Notes:
            Never stripped and never echoed into the error. An empty response
            here would leave an administrator with an account nobody can sign
            in to and no way to tell.
        """
        if not isinstance(value, str) or not value:
            raise MTTemporaryCredentialsResponseInvalidPassword(
                "Invalid temporary_password. A generated password is required."
            )
        return value

    @field_validator("email", mode="before")
    def validate_email(cls, value: Optional[str]) -> str:
        """Validates that the sign-in address is present.

        Args:
            value (Optional[str]): Raw ``email`` value.

        Returns:
            str: The address.

        Raises:
            MTTemporaryCredentialsResponseInvalidEmail: If ``value`` is not a
                non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTemporaryCredentialsResponseInvalidEmail(
                f"Invalid email: {value!r}. Must be a non-empty string."
            )
        return value.strip()
