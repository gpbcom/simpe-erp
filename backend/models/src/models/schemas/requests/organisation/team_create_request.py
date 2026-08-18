from __future__ import annotations

# Standard library imports
from typing import Optional

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.organisation.team.team import Team
from models.schemas.exceptions import (
    MTTeamCreateRequestInvalidAgencyId,
    MTTeamCreateRequestInvalidManagerUserId,
    MTTeamCreateRequestInvalidName,
)


class TeamCreateRequest(BaseModel):
    """The payload forming a team at one of the company's sites.

    Attributes:
        name (str): What the team is called.
        agency_id (str): The site it works from.
        manager_user_id (str): The account that runs it.

    Notes:
        - ``company_id`` is absent and taken from the credential, as everywhere
          else on this surface. It decides whose quotes the team is attributed
          and whose calendar its planning run rewrites.
        - **The member list is absent too**, and that is not an omission. A
          person belongs to exactly one team, so adding somebody to this one
          takes them off another — a consequence worth a deliberate call rather
          than a side effect of creating a team. Members are added afterwards
          through ``PUT /api/v1/teams/{id}/members``. The manager alone is
          enrolled by the creating call, because a team that named a manager who
          was not on it would be a roster missing the person in charge.
        - Whether the named account *may* run a team — that it holds a manager's
          or an administrator's role and belongs to the same site — is checked in
          :class:`~service.organisation.teams.TeamService`, because it is a
          question about other rows.
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
            MTTeamCreateRequestInvalidName: If ``value`` is not a non-empty
                string within :attr:`Team.MAX_NAME_LENGTH`.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamCreateRequestInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        trimmed = value.strip()
        if len(trimmed) > Team.MAX_NAME_LENGTH:
            raise MTTeamCreateRequestInvalidName(
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
            MTTeamCreateRequestInvalidAgencyId: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamCreateRequestInvalidAgencyId(
                f"Invalid agency_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("manager_user_id", mode="before")
    def validate_manager_user_id(cls, value: Optional[str]) -> str:
        """Validates that the team names exactly one manager.

        Args:
            value (Optional[str]): Raw ``manager_user_id`` value.

        Returns:
            str: The trimmed account identifier.

        Raises:
            MTTeamCreateRequestInvalidManagerUserId: If ``value`` is not a
                non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamCreateRequestInvalidManagerUserId(
                f"Invalid manager_user_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_team(self, company_id: str) -> Team:
        """Build the team this payload describes.

        Args:
            company_id (str): The company the caller belongs to.

        Returns:
            Team: The team, with no identifier until it is stored.
        """
        return Team(
            company_id=company_id,
            agency_id=self.agency_id,
            name=self.name,
            manager_user_id=self.manager_user_id,
        )
