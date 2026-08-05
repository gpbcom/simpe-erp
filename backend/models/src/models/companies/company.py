from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, EmailStr, Field, field_validator

from models.companies.company_choice import CompanyChoice

# First-party imports
from models.companies.exceptions import (
    MTCompanyInvalidDate,
    MTCompanyInvalidEmail,
    MTCompanyInvalidId,
    MTCompanyInvalidIsAcceptingApplications,
    MTCompanyInvalidName,
    MTCompanyInvalidRegistrationNumber,
)
from models.geo.postal_address import PostalAddress


class Company(BaseModel):
    """A care agency an assistant can apply to work for.

    Attributes:
        MAX_NAME_LENGTH (ClassVar[int]): Longest accepted trading name.
        MAX_REGISTRATION_LENGTH (ClassVar[int]): Longest accepted registration
            number.
        id (Optional[str]): Identifier, populated on read from the store.
        name (str): Trading name, shown to an applicant choosing between
            agencies.
        registration_number (Optional[str]): The company's registration number.
        contact_email (Optional[EmailStr]): Where an applicant's questions go.
        address (Optional[PostalAddress]): The registered office.
        is_accepting_applications (bool): Whether it appears on the public list
            an applicant chooses from.
        created_at (Optional[datetime]): Creation timestamp, set by the store.
        updated_at (Optional[datetime]): Last-update timestamp, set by the
            store.

    Notes:
        - This exists because an assistant registering themselves has to say
          *which agency they are applying to*. Without it there is nobody to
          route the application to and nobody with standing to approve it.
        - **Only the name and the identifier are ever shown publicly.** The list
          an applicant picks from is served without a credential, so the address
          and contact details stay behind the authenticated routes — publishing
          a directory of agencies with their registered offices is not what
          "choose your employer" needs.
        - ``is_accepting_applications`` is how an agency stops appearing on that
          list without being deleted. A company with assistants and quotes cannot
          be removed, and hiding it is the only honest alternative.
        - The company is *not* a tenancy boundary. Customers, quotes and
          plannings are agency-wide, not scoped per company — see the note in the
          service layer. What a company scopes is who may approve whose
          application.
    """

    MAX_NAME_LENGTH: ClassVar[int] = 200
    MAX_REGISTRATION_LENGTH: ClassVar[int] = 64

    id: Optional[str] = Field(
        default=None, description="Identifier, assigned by the store."
    )
    name: str = Field(description="Trading name.")
    registration_number: Optional[str] = Field(
        default=None, description="Company registration number."
    )
    contact_email: Optional[EmailStr] = Field(
        default=None, description="Where an applicant's questions go."
    )
    address: Optional[PostalAddress] = Field(
        default=None, description="The registered office."
    )
    is_accepting_applications: bool = Field(
        default=True, description="Whether it appears on the public list."
    )
    created_at: Optional[datetime] = Field(
        default=None, description="Creation timestamp."
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Last-update timestamp."
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("id", mode="before")
    def validate_id(cls, value: Union[str, None]) -> Optional[str]:
        """Validates that ``id``, when given, is a non-empty string.

        Args:
            value (Union[str, None]): Raw ``id`` value.

        Returns:
            Optional[str]: The identifier, or ``None`` before it is stored.

        Raises:
            MTCompanyInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTCompanyInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("name", mode="before")
    def validate_name(cls, value: Union[str, None]) -> str:
        """Validates that ``name`` is a usable trading name.

        Args:
            value (Union[str, None]): Raw ``name`` value.

        Returns:
            str: The trimmed name.

        Raises:
            MTCompanyInvalidName: If ``value`` is not a non-empty string within
                :attr:`MAX_NAME_LENGTH`.

        Notes:
            Required, because this is the one field an applicant sees. A
            company with no name is an unlabelled option in a list somebody has
            to choose from.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCompanyInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        trimmed = value.strip()
        if len(trimmed) > cls.MAX_NAME_LENGTH:
            raise MTCompanyInvalidName(
                f"Invalid name: {len(trimmed)} characters. Must be at most "
                f"{cls.MAX_NAME_LENGTH}."
            )
        return trimmed

    @field_validator("registration_number", mode="before")
    def validate_registration_number(cls, value: Union[str, None]) -> Optional[str]:
        """Validates that the registration number, when given, is usable.

        Args:
            value (Union[str, None]): Raw registration-number value.

        Returns:
            Optional[str]: The upper-cased number, or ``None``.

        Raises:
            MTCompanyInvalidRegistrationNumber: If ``value`` is neither
                ``None`` nor a string of alphanumerics within
                :attr:`MAX_REGISTRATION_LENGTH`.

        Notes:
            Upper-cased and stripped of separators so that "123 456 789" and
            "123456789" are the same company. Registration numbers get typed by
            hand from letterheads, and the spacing varies by who is reading.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTCompanyInvalidRegistrationNumber(
                f"Invalid registration_number: {value!r}. Must be a string."
            )
        cleaned = value.replace(" ", "").replace("-", "").upper()
        if not cleaned:
            return None
        if not cleaned.isalnum():
            raise MTCompanyInvalidRegistrationNumber(
                f"Invalid registration_number: {value!r}. Must contain only "
                f"letters and digits."
            )
        if len(cleaned) > cls.MAX_REGISTRATION_LENGTH:
            raise MTCompanyInvalidRegistrationNumber(
                f"Invalid registration_number: {len(cleaned)} characters. Must "
                f"be at most {cls.MAX_REGISTRATION_LENGTH}."
            )
        return cleaned

    @field_validator("contact_email", mode="before")
    def validate_contact_email(cls, value: Union[str, None]) -> Optional[str]:
        """Validates that the contact address, when given, is an address.

        Args:
            value (Union[str, None]): Raw ``contact_email`` value.

        Returns:
            Optional[str]: The lower-cased address, or ``None``.

        Raises:
            MTCompanyInvalidEmail: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTCompanyInvalidEmail(
                f"Invalid contact_email: {value!r}. Must be a non-empty string."
            )
        return value.strip().lower()

    @field_validator("is_accepting_applications", mode="before")
    def validate_is_accepting_applications(cls, value: Union[bool, None]) -> bool:
        """Validates that the open-to-applications flag is a boolean.

        Args:
            value (Union[bool, None]): Raw flag value.

        Returns:
            bool: The flag.

        Raises:
            MTCompanyInvalidIsAcceptingApplications: If ``value`` is neither
                ``None`` nor a boolean.

        Notes:
            Strings are refused rather than coerced. ``"false"`` is truthy, and
            a company that silently kept accepting applications after being
            told to stop would be discovered by the applications arriving.
        """
        if value is None:
            return True
        if not isinstance(value, bool):
            raise MTCompanyInvalidIsAcceptingApplications(
                f"Invalid is_accepting_applications: {value!r}. Must be a boolean."
            )
        return value

    @field_validator("created_at", "updated_at", mode="before")
    def validate_timestamps(
        cls, value: Union[datetime, str, None]
    ) -> Optional[datetime]:
        """Validates that a timestamp is a datetime.

        Args:
            value (Union[datetime, str, None]): Raw timestamp value.

        Returns:
            Optional[datetime]: The timestamp, or ``None``.

        Raises:
            MTCompanyInvalidDate: If ``value`` is neither ``None`` nor a
                datetime or ISO-8601 string.
        """
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                raise MTCompanyInvalidDate(
                    f"Invalid timestamp: {value!r}. Must be an ISO-8601 datetime."
                ) from None
        raise MTCompanyInvalidDate(f"Invalid timestamp: {value!r}. Must be a datetime.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_public_choice(self) -> CompanyChoice:
        """Return the company as an applicant is allowed to see it.

        Returns:
            CompanyChoice: Its identifier and name, and nothing else.

        Notes:
            The list an applicant chooses from is served without a credential.
            Returning the whole record there would publish a directory of every
            agency's registered office and contact address to anybody who asks.
        """
        return CompanyChoice(id=self.id if self.id else "", name=self.name)
