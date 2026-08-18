from __future__ import annotations

# Standard library imports
from decimal import Decimal
from typing import Optional

# Third-party imports
from pydantic import BaseModel, EmailStr, Field, field_validator

from models.geo.postal_address import PostalAddress

# First-party imports
from models.organisation.companies.company import Company
from models.schemas.exceptions import (
    MTCompanyProfileUpdateRequestInvalidBic,
    MTCompanyProfileUpdateRequestInvalidIban,
    MTCompanyProfileUpdateRequestInvalidName,
    MTCompanyProfileUpdateRequestInvalidRegistrationNumber,
)


class CompanyProfileUpdateRequest(BaseModel):
    """The payload an administrator may send about their own agency.

    Attributes:
        name (str): The trading name.
        registration_number (Optional[str]): The SIRET, or ``None``.
        iban (Optional[str]): The account the agency is paid into, or ``None``.
        bic (Optional[str]): That account's bank identifier code, or ``None``.
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
        - ``logo_url`` is absent. The logo is written only by
          ``PUT /api/v1/me/company/logo``, which uploads the object and then
          records where it put it — so no hand-crafted profile payload can
          repoint the field at somebody else's image.

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
    legal_form: Optional[str] = Field(
        default=None,
        description="Legal form, such as SARL, SAS or Association.",
    )
    share_capital: Optional[Decimal] = Field(
        default=None,
        description="Share capital, in euros.",
    )
    rcs_number: Optional[str] = Field(
        default=None,
        description="Trade-register entry.",
    )
    vat_number: Optional[str] = Field(
        default=None,
        description="Intra-community VAT number.",
    )
    phone_number: Optional[str] = Field(
        default=None,
        description="Contact telephone number.",
    )
    iban: Optional[str] = Field(
        default=None,
        description="Account the agency is paid into, or None.",
    )
    bic: Optional[str] = Field(
        default=None,
        description="Bank identifier code of that account, or None.",
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
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a non-empty trading name.

        Args:
            value (Optional[str]): Raw ``name`` value.

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
    def validate_registration_number(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``registration_number`` is absent or plausible.

        Args:
            value (Optional[str]): Raw ``registration_number`` value.

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

    @field_validator("iban", mode="before")
    def validate_iban(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``iban`` is absent or a string.

        Args:
            value (Optional[str]): Raw ``iban`` value.

        Returns:
            Optional[str]: The stripped account number, or ``None``.

        Raises:
            MTCompanyProfileUpdateRequestInvalidIban: If ``value`` is neither
                ``None`` nor a string.

        Notes:
            The shape and the check digits are **not** verified here. That rule
            lives on :class:`~models.organisation.companies.company.Company`, which is what
            the service writes. Duplicating it would mean two definitions of a
            valid IBAN and, sooner or later, two different answers.

            Blank becomes ``None`` rather than an empty string, so "no account
            recorded" and "account recorded as nothing" do not become two
            states that read the same on screen.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTCompanyProfileUpdateRequestInvalidIban(
                f"Invalid iban: {value!r}. Must be a string."
            )
        return value.strip() or None

    @field_validator("bic", mode="before")
    def validate_bic(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``bic`` is absent or a string.

        Args:
            value (Optional[str]): Raw ``bic`` value.

        Returns:
            Optional[str]: The stripped code, or ``None``.

        Raises:
            MTCompanyProfileUpdateRequestInvalidBic: If ``value`` is neither
                ``None`` nor a string.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTCompanyProfileUpdateRequestInvalidBic(
                f"Invalid bic: {value!r}. Must be a string."
            )
        return value.strip() or None

    ############################
    # Publicly Exposed Methods #
    ############################

    def apply_to(self, company: Company) -> Company:
        """Return the agency with this payload's fields written onto it.

        Args:
            company (Company): The agency as it is stored.

        Returns:
            Company: A new agency carrying the submitted values and the
            stored ones this payload does not own.

        Raises:
            MTInvalidCompanyException: If a submitted value does not satisfy
                the domain model — a malformed IBAN, VAT number or share
                capital.

        Notes:
            **Re-validated, not copied.** ``model_copy(update=...)`` writes
            attributes straight onto the new instance without running a single
            validator, so a route built that way stores whatever the payload
            said: an IBAN with a digit wrong, a VAT number of the wrong shape,
            a trading name of any length. Rebuilding through
            ``model_validate`` is what makes the domain rules actually apply to
            the one route that writes these fields.

            The stored record is the base, so ``id``, ``created_at``,
            ``updated_at`` and ``logo_url`` survive — this payload carries none
            of them, and building a fresh :class:`Company` from it alone would
            blank whatever it does not mention.
        """
        merged = company.model_dump()
        merged.update(self.model_dump())
        return Company.model_validate(merged)
