from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional

# Third-party imports
from pydantic import BaseModel, EmailStr, Field, field_validator

# First-party imports
from models.schemas.exceptions import (
    MTCompanyRegistrationRequestInvalidCompanyName,
    MTCompanyRegistrationRequestInvalidEmail,
    MTCompanyRegistrationRequestInvalidFullName,
    MTCompanyRegistrationRequestInvalidPassword,
    MTCompanyRegistrationRequestInvalidRegistrationNumber,
)


class CompanyRegistrationRequest(BaseModel):
    """The payload founding an agency and its first administrator.

    Attributes:
        MIN_PASSWORD_LENGTH (ClassVar[int]): Shortest password accepted.
        MAX_PASSWORD_BYTES (ClassVar[int]): Longest password accepted, matching
            what bcrypt can actually hash.
        company_name (str): The trading name of the agency being founded.
        registration_number (Optional[str]): The agency's registration number.
        full_name (str): The founder's display name.
        email (EmailStr): The founder's sign-in address.
        password (str): The founder's plaintext password.

    Notes:
        - **There is no ``company_id`` field, and there must never be one.**
          This payload arrives unauthenticated and its author is granted
          administrator rights over the company it creates. A field naming an
          *existing* company would therefore be a field granting administrator
          rights over somebody else's agency to whoever asked — the same
          mistake the ``role`` field on :class:`RegisterRequest` used to be.
          The company is always new, so the rights are always over nothing that
          existed a moment ago.
        - There is no ``role`` field either, for the same reason. The role is
          decided by the route, not by the caller.
        - The password rules match :class:`RegisterRequest` exactly. bcrypt
          silently ignores anything past 72 bytes, so a longer password would
          appear accepted while only its first 72 bytes ever mattered; the
          limit is measured in **bytes** because an accented or emoji-bearing
          password reaches it sooner than its length suggests.
        - No address is taken. Founding an agency should cost one screen, and
          :class:`~models.geo.postal_address.PostalAddress` geocodes during
          validation — a required address would put a live Nominatim lookup on
          the sign-up path, where a slow third party would read as a broken
          form. The founder fills it in afterwards, from the company screen.
    """

    MIN_PASSWORD_LENGTH: ClassVar[int] = 12
    MAX_PASSWORD_BYTES: ClassVar[int] = 72

    company_name: str = Field(description="The trading name of the agency.")
    registration_number: Optional[str] = Field(
        default=None,
        description="The agency's registration number, if it has one yet.",
    )
    full_name: str = Field(description="The founder's display name.")
    email: EmailStr = Field(description="The founder's sign-in address.")
    password: str = Field(description="The founder's plaintext password.")

    @field_validator("company_name", mode="before")
    def validate_company_name(cls, value: Optional[str]) -> str:
        """Validates that ``company_name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``company_name`` value.

        Returns:
            str: The trimmed trading name.

        Raises:
            MTCompanyRegistrationRequestInvalidCompanyName: If ``value`` is not
                a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCompanyRegistrationRequestInvalidCompanyName(
                f"Invalid company_name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("registration_number", mode="before")
    def validate_registration_number(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``registration_number`` is ``None`` or non-empty.

        Args:
            value (Optional[str]): Raw ``registration_number`` value.

        Returns:
            Optional[str]: The trimmed number, or ``None``.

        Raises:
            MTCompanyRegistrationRequestInvalidRegistrationNumber: If ``value``
                is neither ``None`` nor a non-empty string.

        Notes:
            Optional because an agency being founded may not have been
            registered yet, and refusing to let it exist until it has would
            put the paperwork before the product.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTCompanyRegistrationRequestInvalidRegistrationNumber(
                f"Invalid registration_number: {value!r}. Must be a non-empty "
                f"string or None."
            )
        return value.strip()

    @field_validator("full_name", mode="before")
    def validate_full_name(cls, value: Optional[str]) -> str:
        """Validates that ``full_name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``full_name`` value.

        Returns:
            str: The stripped display name.

        Raises:
            MTCompanyRegistrationRequestInvalidFullName: If ``value`` is not a
                non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCompanyRegistrationRequestInvalidFullName(
                f"Invalid full_name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("email", mode="before")
    def validate_email(cls, value: Optional[str]) -> str:
        """Validates that ``email`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``email`` value.

        Returns:
            str: The stripped, lower-cased address.

        Raises:
            MTCompanyRegistrationRequestInvalidEmail: If ``value`` is not a
                non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCompanyRegistrationRequestInvalidEmail(
                f"Invalid email: {value!r}. Must be a non-empty string."
            )
        return value.strip().lower()

    @field_validator("password", mode="before")
    def validate_password(cls, value: Optional[str]) -> str:
        """Validates that ``password`` is within the accepted length range.

        Args:
            value (Optional[str]): Raw ``password`` value.

        Returns:
            str: The password, unmodified.

        Raises:
            MTCompanyRegistrationRequestInvalidPassword: If ``value`` is not a
                string, is shorter than :attr:`MIN_PASSWORD_LENGTH`, or is
                longer than :attr:`MAX_PASSWORD_BYTES` when encoded.

        Notes:
            The password is never stripped, and never appears in an error
            message. Both would leak it: one into the stored credential, the
            other into the logs.
        """
        if not isinstance(value, str):
            raise MTCompanyRegistrationRequestInvalidPassword(
                "Invalid password. Must be a string."
            )
        if len(value) < cls.MIN_PASSWORD_LENGTH:
            raise MTCompanyRegistrationRequestInvalidPassword(
                f"Invalid password. Must be at least "
                f"{cls.MIN_PASSWORD_LENGTH} characters."
            )
        if len(value.encode("utf-8")) > cls.MAX_PASSWORD_BYTES:
            raise MTCompanyRegistrationRequestInvalidPassword(
                f"Invalid password. Must be at most {cls.MAX_PASSWORD_BYTES} "
                f"bytes once encoded; anything beyond that is silently ignored."
            )
        return value
