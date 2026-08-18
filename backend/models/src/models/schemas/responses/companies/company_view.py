from __future__ import annotations

# Standard library imports
from datetime import datetime
from decimal import Decimal
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.organisation.companies.company import Company
from models.geo.postal_address import PostalAddress
from models.schemas.exceptions import (
    MTCompanyViewInvalidIbanMaskFlag,
    MTCompanyViewInvalidName,
)


class CompanyView(BaseModel):
    """An agency as a caller who is not its administrator may read it.

    Attributes:
        id (Optional[str]): Identifier, as stored.
        name (str): Trading name.
        legal_form (Optional[str]): Legal form, such as SARL or Association.
        share_capital (Optional[Decimal]): Share capital, in euros.
        rcs_number (Optional[str]): Trade-register entry.
        vat_number (Optional[str]): Intra-community VAT number.
        phone_number (Optional[str]): Contact telephone number.
        registration_number (Optional[str]): Company registration number.
        contact_email (Optional[str]): Where an applicant's questions go.
        address (Optional[PostalAddress]): The registered office.
        iban (Optional[str]): The account number, whole or masked depending on
            who asked.
        iban_is_masked (bool): Whether ``iban`` carries bullets rather than the
            account number.
        bic (Optional[str]): Bank identifier code of that account.
        logo_url (Optional[str]): URL of the agency's logo.
        is_accepting_applications (bool): Whether it appears publicly.
        created_at (Optional[datetime]): Creation timestamp.
        updated_at (Optional[datetime]): Last-update timestamp.

    Notes:
        - **The shape is the permission**, as with
          :class:`~models.organisation.companies.company_choice.CompanyChoice`. The agency
          routes a *manager* can reach return this rather than a whole
          :class:`~models.organisation.companies.company.Company`, so however the service
          changes they cannot hand back a bank account somebody could pay into.
          An administrator reads their own agency in full at
          ``GET /api/v1/me/company``.
        - ``iban_is_masked`` travels with the number rather than being inferred
          from it. A client deciding by looking for bullets would have to guess,
          and the one thing it must never do is echo a masked value back into an
          update — which would overwrite the real account with its own censoring.
        - The masking itself belongs to
          :meth:`~models.organisation.companies.company.Company.masked_iban`, not here. One
          rule in one place, testable without a request.
        - No validator re-checks the IBAN's shape: by the time it reaches this
          model it is either a value :class:`Company` already validated or a
          deliberately malformed mask, and refusing the mask would make the
          protection unrepresentable.
    """

    id: Optional[str] = Field(default=None, description="Identifier, as stored.")
    name: str = Field(description="Trading name.")
    legal_form: Optional[str] = Field(default=None, description="Legal form.")
    share_capital: Optional[Decimal] = Field(
        default=None, description="Share capital, in euros."
    )
    rcs_number: Optional[str] = Field(default=None, description="Trade-register entry.")
    vat_number: Optional[str] = Field(
        default=None, description="Intra-community VAT number."
    )
    phone_number: Optional[str] = Field(
        default=None, description="Contact telephone number."
    )
    registration_number: Optional[str] = Field(
        default=None, description="Company registration number."
    )
    contact_email: Optional[str] = Field(
        default=None, description="Where an applicant's questions go."
    )
    address: Optional[PostalAddress] = Field(
        default=None, description="The registered office."
    )
    iban: Optional[str] = Field(
        default=None, description="The account number, whole or masked."
    )
    iban_is_masked: bool = Field(
        default=True, description="Whether the account number is masked."
    )
    bic: Optional[str] = Field(
        default=None, description="Bank identifier code of the account."
    )
    logo_url: Optional[str] = Field(
        default=None, description="URL of the agency's logo."
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

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a usable trading name.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The trimmed name.

        Raises:
            MTCompanyViewInvalidName: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCompanyViewInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("iban_is_masked", mode="before")
    def validate_iban_is_masked(cls, value: Union[bool, None]) -> bool:
        """Validates that the masking flag is a boolean.

        Args:
            value (Union[bool, None]): Raw flag value.

        Returns:
            bool: The flag, defaulting to masked when unset.

        Raises:
            MTCompanyViewInvalidIbanMaskFlag: If ``value`` is neither ``None``
                nor a boolean.

        Notes:
            Absent means *masked*. The safe default for a flag that gates a
            bank account is the one that reveals nothing, so a caller that
            forgets to set it under-shares rather than over-shares.
        """
        if value is None:
            return True
        if not isinstance(value, bool):
            raise MTCompanyViewInvalidIbanMaskFlag(
                f"Invalid iban_is_masked: {value!r}. Must be a boolean."
            )
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    @classmethod
    def from_company(cls, company: Company, reveal: bool) -> CompanyView:
        """Project an agency for a given caller.

        Args:
            company (Company): The agency to project.
            reveal (bool): Whether the caller may read the account number in
                full. Administrators may. Nobody else does.

        Returns:
            CompanyView: The agency, with its IBAN whole or masked.

        Notes:
            ``reveal`` is a parameter rather than a role lookup because a model
            has no business knowing what an administrator is. The route decides,
            which keeps the decision beside the dependency that already
            authenticated the caller.
        """
        return cls(
            id=company.id,
            name=company.name,
            legal_form=company.legal_form,
            share_capital=company.share_capital,
            rcs_number=company.rcs_number,
            vat_number=company.vat_number,
            phone_number=company.phone_number,
            registration_number=company.registration_number,
            contact_email=(
                str(company.contact_email) if company.contact_email else None
            ),
            address=company.address,
            iban=company.iban if reveal else company.masked_iban(),
            iban_is_masked=not reveal,
            bic=company.bic,
            logo_url=company.logo_url,
            is_accepting_applications=company.is_accepting_applications,
            created_at=company.created_at,
            updated_at=company.updated_at,
        )
