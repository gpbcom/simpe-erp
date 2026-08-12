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
    MTAgencyUpdateRequestInvalidName,
    MTAgencyUpdateRequestInvalidType,
)


class AgencyUpdateRequest(BaseModel):
    """The payload changing a site's name, address or type.

    Attributes:
        name (str): What the site is called.
        address (Optional[PostalAddress]): Where it is.
        agency_type (AgencyType): What it is used for.

    Notes:
        - The same three fields as
          :class:`~models.schemas.requests.organisation.agency_create_request.AgencyCreateRequest`
          and for the same reason: a site's *legal identity* is its company's,
          and is changed on the company's own screens. A payload here that could
          carry an IBAN would let a site's address form rewrite the account every
          invoice is paid into.
        - The whole set is sent rather than the changed field, matching every
          other ``PUT`` on this surface. A partial payload cannot express
          *clearing* an address — the field would be absent either way — and
          "the site now has no address" is a thing an administrator legitimately
          means.
        - Whether the type may actually change is decided in
          :class:`~service.organisation.agencies.AgencyService`, which refuses to
          promote a branch or demote the head office. It is a question about the
          company's other sites, which a payload cannot answer about itself.
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
            MTAgencyUpdateRequestInvalidName: If ``value`` is not a non-empty
                string within :attr:`Agency.MAX_NAME_LENGTH`.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTAgencyUpdateRequestInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        trimmed = value.strip()
        if len(trimmed) > Agency.MAX_NAME_LENGTH:
            raise MTAgencyUpdateRequestInvalidName(
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
            MTAgencyUpdateRequestInvalidType: If ``value`` is neither ``None``
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
            raise MTAgencyUpdateRequestInvalidType(
                f"Invalid agency_type: {value!r}. Must be one of "
                f"{', '.join(AgencyType.values())}."
            )
        return AgencyType(value.strip().lower())

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_agency(self, agency_id: str, company_id: str) -> Agency:
        """Build the site this payload describes.

        Args:
            agency_id (str): The site being changed, taken from the route.
            company_id (str): The company the caller belongs to.

        Returns:
            Agency: The proposed site.

        Notes:
            The identifier comes from the path and the company from the
            credential, so neither can be moved by the body. The service still
            re-reads the stored site and keeps its legal identity: what this
            object carries is the *three site fields*, not a replacement record.
        """
        return Agency(
            id=agency_id,
            company_id=company_id,
            name=self.name,
            address=self.address,
            agency_type=self.agency_type,
        )
