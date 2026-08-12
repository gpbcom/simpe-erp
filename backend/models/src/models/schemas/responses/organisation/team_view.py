from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.organisation.team.team import Team
from models.schemas.exceptions import (
    MTTeamViewInvalidCount,
    MTTeamViewInvalidName,
)


class TeamView(BaseModel):
    """A team as every route returns it.

    Attributes:
        id (Optional[str]): Identifier, as stored.
        company_id (str): The company the team belongs to.
        agency_id (str): The site the team works from.
        name (str): What the team is called.
        manager_user_id (str): The account that runs it.
        member_count (int): How many people are on it.
        created_at (Optional[datetime]): Creation timestamp.
        updated_at (Optional[datetime]): Last-update timestamp.

    Notes:
        - The team record carries nothing sensitive, so this adds one field to
          it rather than hiding any: the **member count**, which the teams grid
          shows on every row. Resolved per row it would be a query per team.
        - The site's name and the manager's name are deliberately **not**
          resolved here. Both are lists the screen already holds — it needs them
          to offer the pickers on the same page — and joining them server-side
          would put two more tables in a statement that is read on every
          navigation.
    """

    id: Optional[str] = Field(default=None, description="Identifier, as stored.")
    company_id: str = Field(description="The company the team belongs to.")
    agency_id: str = Field(description="The site the team works from.")
    name: str = Field(description="What the team is called.")
    manager_user_id: str = Field(description="The account that runs the team.")
    member_count: int = Field(default=0, description="How many people are on the team.")
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
        """Validates that ``name`` is a usable team name.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The trimmed name.

        Raises:
            MTTeamViewInvalidName: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTTeamViewInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("member_count", mode="before")
    def validate_member_count(cls, value: Union[int, None]) -> int:
        """Validates that ``member_count`` is a non-negative integer.

        Args:
            value (Union[int, None]): Raw ``member_count`` value.

        Returns:
            int: The count, defaulting to zero when unset.

        Raises:
            MTTeamViewInvalidCount: If ``value`` is negative, or is not an
                integer.

        Notes:
            Zero is accepted although a stored team always has at least its
            manager on it. The count is read from a separate statement, and a
            model that refused zero would turn a race with a membership change
            into a failed page.
        """
        if value is None:
            return 0
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTTeamViewInvalidCount(
                f"Invalid member_count: {value!r}. Must be an integer."
            )
        if value < 0:
            raise MTTeamViewInvalidCount(
                f"Invalid member_count: {value!r}. Must not be negative."
            )
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    @classmethod
    def from_team(cls, team: Team, member_count: int = 0) -> TeamView:
        """Project a team for a caller.

        Args:
            team (Team): The team to project.
            member_count (int): How many people are on it.

        Returns:
            TeamView: The team.
        """
        return cls(
            id=team.id,
            company_id=team.company_id,
            agency_id=team.agency_id,
            name=team.name,
            manager_user_id=team.manager_user_id,
            member_count=member_count,
            created_at=team.created_at,
            updated_at=team.updated_at,
        )
