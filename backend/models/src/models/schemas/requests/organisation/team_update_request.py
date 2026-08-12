from __future__ import annotations

# Standard library imports
from typing import Optional

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.organisation.team.team import Team
from models.schemas.exceptions import (
    MTTeamUpdateRequestInvalidAgencyId,
    MTTeamUpdateRequestInvalidManagerUserId,
    MTTeamUpdateRequestInvalidName,
)


class TeamUpdateRequest(BaseModel):
    """The payload changing a team's name, site or manager.

    Attributes:
        name (str): What the team is called.
        agency_id (str): The site it works from.
        manager_user_id (str): The account that runs it.

    Notes:
        - **Moving a team to another site changes where its work comes from**,
          because every distance a quote is attributed by is measured from the
          site. It is offered here rather than forbidden, since a branch that
          relocates is an ordinary event — but the service re-checks that the
          manager belongs to the new site, and the members do not follow
          automatically.
        - The member list is absent, as it is on creation: membership is one
          person leaving one team for another, and is changed by its own call.
    """

    name: str = Field(description="What the team is called.")
    agency_id: str = Field(description="The site the team works from.")
    manager_user_id: str = Field(description="The account that runs the team.")

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a usable team name.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The trimmed name.

        Raises:
            MTTeamUpdateRequestInvalidName: If ``value`` is not a non-empty
                string within :attr:`Team.MAX_NAME_LENGTH`.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamUpdateRequestInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        trimmed = value.strip()
        if len(trimmed) > Team.MAX_NAME_LENGTH:
            raise MTTeamUpdateRequestInvalidName(
                f"Invalid name: {len(trimmed)} characters. Must be at most "
                f"{Team.MAX_NAME_LENGTH}."
            )
        return trimmed

    @field_validator("agency_id", mode="before")
    def validate_agency_id(cls, value: Optional[str]) -> str:
        """Validates that the site the team works from is named.

        Args:
            value (Optional[str]): Raw ``agency_id`` value.

        Returns:
            str: The trimmed identifier.

        Raises:
            MTTeamUpdateRequestInvalidAgencyId: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamUpdateRequestInvalidAgencyId(
                f"Invalid agency_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("manager_user_id", mode="before")
    def validate_manager_user_id(cls, value: Optional[str]) -> str:
        """Validates that the team still names exactly one manager.

        Args:
            value (Optional[str]): Raw ``manager_user_id`` value.

        Returns:
            str: The trimmed account identifier.

        Raises:
            MTTeamUpdateRequestInvalidManagerUserId: If ``value`` is not a
                non-empty string.

        Notes:
            Required rather than optional, so an update cannot leave a team
            without one. A team with no manager is a team whose planning nobody
            may re-compute.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamUpdateRequestInvalidManagerUserId(
                f"Invalid manager_user_id: {value!r}. "  # noqa: E501
                "Must be a non-empty string."
            )
        return value.strip()

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_team(self, team_id: str, company_id: str) -> Team:
        """Build the team this payload describes.

        Args:
            team_id (str): The team being changed, taken from the route.
            company_id (str): The company the caller belongs to.

        Returns:
            Team: The proposed team.
        """
        return Team(
            id=team_id,
            company_id=company_id,
            agency_id=self.agency_id,
            name=self.name,
            manager_user_id=self.manager_user_id,
        )
