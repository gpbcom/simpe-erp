from __future__ import annotations

# Standard library imports
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, EmailStr, Field, field_validator

# First-party imports
from models.geo.postal_address import PostalAddress
from models.schemas.exceptions import (
    MTCompanyProfileUpdateRequestInvalidName,
    MTCompanyProfileUpdateRequestInvalidRegistrationNumber,
)


class CompanyProfileUpdateRequest(BaseModel):
    """The payload an administrator may send about their own agency.

    Attributes:
        name (str): The trading name.
        registration_number (Optional[str]): The SIRET, or ``None``.
        contact_email (Optional[EmailStr]): Where applicants write, or ``None``.
        address (Optional[PostalAddress]): The registered address, or ``None``.
        is_accepting_applications (bool): Whether the agency appears on the
            public list an applicant chooses from.

    Notes:
        **The shape of this model is the permission**, as elsewhere in this
        package. What it cannot carry matters more than what it can:

        - ``id`` is taken from the caller's own account, so an administrator of
          one agency cannot address another's. The agency-wide
          ``PUT /api/v1/companies/{id}`` still exists for the case where an
          administrator genuinely means to name one.
        - ``created_at`` and ``updated_at`` are records of what happened.

        ``is_accepting_applications`` *is* here, even though
        ``PATCH /api/v1/companies/{id}/applications`` can also set it. It is
        agency information an administrator owns, it sits on the same screen as
        the rest of it, and both paths call the same service — so the rule has
        one implementation and two doors, rather than two implementations.
    """

    name: str = Field(description="The trading name.")
    registration_number: Optional[str] = Field(
        default=None, description="The SIRET, or None."
    )
    contact_email: Optional[EmailStr] = Field(
        default=None, description="Where applicants write, or None."
    )
    address: Optional[PostalAddress] = Field(
        default=None, description="The registered address, or None."
    )
    is_accepting_applications: bool = Field(
        default=True, description="Whether the agency is open to applicants."
    )

    @field_validator("name", mode="before")
    def validate_name(cls, value: Union[str, None]) -> str:
        """Validates that ``name`` is a non-empty trading name.

        Args:
            value (Union[str, None]): Raw ``name`` value.

        Returns:
            str: The stripped trading name.

        Raises:
            MTCompanyProfileUpdateRequestInvalidName: If ``value`` is missing or
                blank once stripped.

        Notes:
            An agency with no name is the one field nothing else can work
            around: it heads every quote the agency prints, and it is what an
            applicant picks from on the public list.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCompanyProfileUpdateRequestInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty trading name."
            )
        return value.strip()

    @field_validator("registration_number", mode="before")
    def validate_registration_number(cls, value: Union[str, None]) -> Optional[str]:
        """Validates that ``registration_number`` is absent or plausible.

        Args:
            value (Union[str, None]): Raw ``registration_number`` value.

        Returns:
            Optional[str]: The stripped number, or ``None``.

        Raises:
            MTCompanyProfileUpdateRequestInvalidRegistrationNumber: If ``value``
                is neither ``None`` nor a string.

        Notes:
            Blank becomes ``None`` rather than an empty string. A form submits
            an untouched field as ``""``, and storing that would make "no SIRET
            recorded" and "SIRET recorded as nothing" two different states that
            read the same on screen.

            The digits are not checked. A SIRET has a defined length and a
            checksum, but agencies exist that have not been issued one yet, and
            refusing to save the rest of the form over a field the law does not
            require here would be the wrong trade.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTCompanyProfileUpdateRequestInvalidRegistrationNumber(
                f"Invalid registration_number: {value!r}. Must be a string."
            )
        return value.strip() or None
