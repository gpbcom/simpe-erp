from __future__ import annotations

# Standard library imports
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import AgencyType
from models.geo.postal_address import PostalAddress
from models.organisation.agency.agency import Agency
from models.schemas.exceptions import (
    MTAgencyCreateRequestInvalidName,
    MTAgencyCreateRequestInvalidType,
)


class AgencyCreateRequest(BaseModel):
    """The payload opening a new site for the caller's company.

    Attributes:
        name (str): What the site is called.
        address (Optional[PostalAddress]): Where it is.
        agency_type (AgencyType): What it is used for.

    Notes:
        - **The shape of this model is the permission.**
          :class:`~models.organisation.agency.agency.Agency` subclasses
          :class:`~models.organisation.companies.company.Company` and therefore
          carries the SIRET, the VAT number and the account money is paid into.
          A route taking a whole ``Agency`` as its body would let an
          administrator of one company file a site under another's identity, and
          set the IBAN that every invoice is printed with. None of those fields
          exist here, so no payload can carry them. The head office inherits
          them from its company inside
          :class:`~service.organisation.agencies.AgencyService`.
        - ``company_id`` is absent for the same reason it is absent from
          :class:`~models.schemas.requests.quoting.quote_create_request.QuoteCreateRequest`:
          it decides whose business the site belongs to, and is taken from the
          credential in the route.
        - ``agency_type`` **is** accepted and then **overwritten** by the
          service — the first site of a company is its head office and every
          later one a branch. It is kept in the payload so the field exists for
          the day a deliberate promotion is offered, and so a client sending it
          is not answered with a validation error for a field the API documents.
    """

    name: str = Field(description="What the site is called.")
    address: Optional[PostalAddress] = Field(
        default=None, description="Where the site is."
    )
    agency_type: AgencyType = Field(
        default=AgencyType.OFFICE, description="What the site is used for."
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a usable site name.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The trimmed name.

        Raises:
            MTAgencyCreateRequestInvalidName: If ``value`` is not a non-empty
                string within :attr:`Agency.MAX_NAME_LENGTH`.

        Notes:
            The length is read from the model rather than restated, so the
            payload and the record it becomes can never disagree about what
            fits.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTAgencyCreateRequestInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        trimmed = value.strip()
        if len(trimmed) > Agency.MAX_NAME_LENGTH:
            raise MTAgencyCreateRequestInvalidName(
                f"Invalid name: {len(trimmed)} characters. Must be at most "
                f"{Agency.MAX_NAME_LENGTH}."
            )
        return trimmed

    @field_validator("agency_type", mode="before")
    def validate_agency_type(cls, value: Union[AgencyType, str, None]) -> AgencyType:  # noqa: E501
        """Validates that ``agency_type`` names a known kind of site.

        Args:
            value (Union[AgencyType, str, None]): Raw ``agency_type`` value.

        Returns:
            AgencyType: The resolved type, defaulting to a branch office.

        Raises:
            MTAgencyCreateRequestInvalidType: If ``value`` is neither ``None``
                nor a known type.
        """
        if value is None:
            return AgencyType.OFFICE
        if isinstance(value, AgencyType):
            return value
        if (
            not isinstance(value, str)
            or value.strip().lower() not in AgencyType.values()
        ):  # noqa: E501
            raise MTAgencyCreateRequestInvalidType(
                f"Invalid agency_type: {value!r}. Must be one of "
                f"{', '.join(AgencyType.values())}."
            )
        return AgencyType(value.strip().lower())

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_agency(self, company_id: str) -> Agency:
        """Build the site this payload describes.

        Args:
            company_id (str): The company the caller belongs to.

        Returns:
            Agency: The site, carrying no legal identity of its own.

        Notes:
            The company comes from the caller rather than the body, which is the
            whole reason this method exists instead of
            ``Agency(**payload.model_dump())``.
        """
        return Agency(
            company_id=company_id,
            name=self.name,
            address=self.address,
            agency_type=self.agency_type,
        )
