from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional

# Third-party imports
from pydantic import (  # noqa: E501
    BaseModel,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

# First-party imports
from models.schemas.exceptions import (
    MTRegisterRequestInvalidEmail,
    MTRegisterRequestInvalidFullName,
    MTRegisterRequestInvalidHcaId,
    MTRegisterRequestInvalidPassword,
)


class RegisterRequest(BaseModel):
    """The payload creating an account.

    Attributes:
        MIN_PASSWORD_LENGTH (ClassVar[int]): Shortest password accepted.
        MAX_PASSWORD_BYTES (ClassVar[int]): Longest password accepted, matching
            what bcrypt can actually hash.
        email (EmailStr): The sign-in address.
        full_name (str): The display name.
        password (str): The plaintext password.
        hca_id (Optional[str]): The assistant record to link.

    Notes:
        - **There is no ``role`` field, deliberately.** This payload arrives on
          the one unauthenticated route that creates an account, so a role named
          here would be a role granted to whoever asked for it: anybody could
          register themselves an administrator. Self-registration always
          produces an assistant, and a privileged account is created only
          through the manager-gated staff-account route.
        - The upper bound on the password is not arbitrary. bcrypt silently
          ignores anything past 72 bytes, so a longer password would appear to be
          accepted while only its first 72 bytes ever mattered — a user could
          change the tail and still sign in. Rejecting it is honest.
        - The length is measured in **bytes**, not characters: an accented or
          emoji-bearing password reaches the limit sooner than its length
          suggests.
    """

    MIN_PASSWORD_LENGTH: ClassVar[int] = 12
    MAX_PASSWORD_BYTES: ClassVar[int] = 72

    email: EmailStr = Field(description="The sign-in address.")
    full_name: str = Field(description="The display name.")
    password: str = Field(description="The plaintext password.")
    hca_id: Optional[str] = Field(
        default=None,
        description="The assistant record to link, for an assistant account.",
    )

    @field_validator("email", mode="before")
    def validate_email(cls, value: Optional[str]) -> str:
        """Validates that ``email`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``email`` value.

        Returns:
            str: The stripped, lower-cased address.

        Raises:
            MTRegisterRequestInvalidEmail: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTRegisterRequestInvalidEmail(
                f"Invalid email: {value!r}. Must be a non-empty string."
            )
        return value.strip().lower()

    @field_validator("full_name", mode="before")
    def validate_full_name(cls, value: Optional[str]) -> str:
        """Validates that ``full_name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``full_name`` value.

        Returns:
            str: The stripped display name.

        Raises:
            MTRegisterRequestInvalidFullName: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTRegisterRequestInvalidFullName(
                f"Invalid full_name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("password", mode="before")
    def validate_password(cls, value: Optional[str]) -> str:
        """Validates that ``password`` is within the accepted length range.

        Args:
            value (Optional[str]): Raw ``password`` value.

        Returns:
            str: The password, unmodified.

        Raises:
            MTRegisterRequestInvalidPassword: If ``value`` is not a string, is
                shorter than :attr:`MIN_PASSWORD_LENGTH`, or is longer than
                :attr:`MAX_PASSWORD_BYTES` when encoded.

        Notes:
            The password is never stripped, and never appears in an error
            message. Both would leak it: one into the stored credential, the
            other into the logs.
        """
        if not isinstance(value, str):
            raise MTRegisterRequestInvalidPassword(
                "Invalid password. Must be a string."
            )
        if len(value) < cls.MIN_PASSWORD_LENGTH:
            raise MTRegisterRequestInvalidPassword(
                f"Invalid password. Must be at least "
                f"{cls.MIN_PASSWORD_LENGTH} characters."
            )
        if len(value.encode("utf-8")) > cls.MAX_PASSWORD_BYTES:
            raise MTRegisterRequestInvalidPassword(
                f"Invalid password. Must be at most {cls.MAX_PASSWORD_BYTES} "
                f"bytes once encoded; anything beyond that is silently ignored."
            )
        return value

    @field_validator("hca_id", mode="before")
    def validate_hca_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``hca_id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``hca_id`` value.

        Returns:
            Optional[str]: The assistant identifier, or ``None``.

        Raises:
            MTRegisterRequestInvalidHcaId: If ``value`` is neither ``None`` nor
                a non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTRegisterRequestInvalidHcaId(
                f"Invalid hca_id: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @model_validator(mode="after")
    def check_hca_link(self) -> RegisterRequest:
        """Ensure an assistant account names an assistant record.

        Returns:
            RegisterRequest: ``self`` for chaining.

        Raises:
            MTRegisterRequestInvalidHcaId: If no ``hca_id`` is given.

        Notes:
            - Caught at the request boundary so the caller gets a 422 naming the
              field, rather than a foreign-key error surfacing as a 500.
            - The check is unconditional because this route now only ever
              creates an assistant account. It used to be conditional on a
              ``role`` field that the payload carried, which is exactly the
              field that let a caller register themselves an administrator.
        """
        if self.hca_id is None:
            raise MTRegisterRequestInvalidHcaId(
                "Invalid hca_id: an account with the 'hca' role must name the "
                "assistant record it belongs to."
            )
        return self
