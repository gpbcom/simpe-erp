from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import AgencyType
from models.geo.postal_address import PostalAddress
from models.organisation.agency.agency import Agency
from models.schemas.exceptions import (
    MTAgencyViewInvalidCount,
    MTAgencyViewInvalidName,
)


class AgencyView(BaseModel):
    """A site as every route returns it.

    Attributes:
        id (Optional[str]): Identifier, as stored.
        company_id (str): The company the site belongs to.
        name (str): What the site is called.
        agency_type (AgencyType): What it is used for.
        address (Optional[PostalAddress]): Where it is.
        is_headquarters (bool): Whether it is the company's head office.
        member_count (int): How many people are attached to it.
        team_count (int): How many teams work from it.
        created_at (Optional[datetime]): Creation timestamp.
        updated_at (Optional[datetime]): Last-update timestamp.

    Notes:
        - **The shape is the permission, and here it is the whole protection.**
          :class:`~models.organisation.agency.agency.Agency` subclasses
          :class:`~models.organisation.companies.company.Company`, so the record
          behind this carries the SIRET, the VAT number and the IBAN. Reads are
          open to every signed-in member of the company — an assistant needs to
          know which sites exist — and returning the record itself would put the
          company's bank account on that screen. Not one legal field is declared
          here, so no change to the service can leak one. An administrator reads
          the legal identity at ``GET /api/v1/companies/{id}``, which masks the
          account for anybody who is not one.
        - ``is_headquarters`` travels rather than being inferred from
          ``agency_type``. A client comparing against the literal ``"hq"`` would
          break silently the day a fourth kind of site is added.
        - The two counts are **carried on the row** because the list is a grid
          that shows them. Resolved per row they would be a query per site, and
          the repository already computes both in one statement each.
    """

    id: Optional[str] = Field(default=None, description="Identifier, as stored.")
    company_id: str = Field(description="The company the site belongs to.")
    name: str = Field(description="What the site is called.")
    agency_type: AgencyType = Field(description="What the site is used for.")
    address: Optional[PostalAddress] = Field(
        default=None, description="Where the site is."
    )
    is_headquarters: bool = Field(
        default=False, description="Whether it is the head office."
    )
    member_count: int = Field(
        default=0, description="How many people are attached to the site."
    )
    team_count: int = Field(default=0, description="How many teams work from the site.")
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
        """Validates that ``name`` is a usable site name.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The trimmed name.

        Raises:
            MTAgencyViewInvalidName: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTAgencyViewInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("member_count", "team_count", mode="before")
    def validate_counts(cls, value: Union[int, None]) -> int:
        """Validates that a headline count is a non-negative integer.

        Args:
            value (Union[int, None]): Raw count value.

        Returns:
            int: The count, defaulting to zero when unset.

        Raises:
            MTAgencyViewInvalidCount: If ``value`` is negative, or is not an
                integer.

        Notes:
            Booleans are refused explicitly: ``True`` is an ``int`` in Python,
            and a count of one would read on screen as a site with a single
            member rather than as a bug.
        """
        if value is None:
            return 0
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTAgencyViewInvalidCount(
                f"Invalid count: {value!r}. Must be an integer."
            )
        if value < 0:
            raise MTAgencyViewInvalidCount(
                f"Invalid count: {value!r}. Must not be negative."
            )
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    @classmethod
    def from_agency(
        cls, agency: Agency, member_count: int = 0, team_count: int = 0
    ) -> AgencyView:
        """Project a site for a caller.

        Args:
            agency (Agency): The site to project.
            member_count (int): How many people are attached to it.
            team_count (int): How many teams work from it.

        Returns:
            AgencyView: The site, with no legal identity attached.

        Notes:
            The counts default to zero rather than being computed here, because
            a model cannot query. A route that has just created a site passes
            nothing and is exactly right: it has neither members nor teams yet.
        """
        return cls(
            id=agency.id,
            company_id=agency.company_id,
            name=agency.name,
            agency_type=agency.agency_type,
            address=agency.address,
            is_headquarters=agency.is_headquarters(),
            member_count=member_count,
            team_count=team_count,
            created_at=agency.created_at,
            updated_at=agency.updated_at,
        )
