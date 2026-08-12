from __future__ import annotations

# Standard library imports
from typing import Optional

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import MTQuoteTeamRequestInvalidTeamId


class QuoteTeamRequest(BaseModel):
    """The payload moving a quote to a different team.

    Attributes:
        team_id (str): The team that will deliver the work instead.

    Notes:
        One field, and it still earns a model rather than a query parameter. The
        team decides whose week the planner rewrites, so the change deserves a
        body a client has to compose deliberately — the same reason
        ``PATCH /api/v1/users/{id}/role`` takes one.
    """

    team_id: str = Field(description="The team that will deliver the work.")

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("team_id", mode="before")
    def validate_team_id(cls, value: Optional[str]) -> str:
        """Validates that ``team_id`` names a team.

        Args:
            value (Optional[str]): Raw ``team_id`` value.

        Returns:
            str: The trimmed identifier.

        Raises:
            MTQuoteTeamRequestInvalidTeamId: If ``value`` is not a non-empty
                string.

        Notes:
            There is no "no team" value, and there must not be. A quote with no
            team is read by no planning run, so clearing the field would make
            the work disappear from every calendar while still looking accepted
            on the quote screen.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteTeamRequestInvalidTeamId(
                f"Invalid team_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()
