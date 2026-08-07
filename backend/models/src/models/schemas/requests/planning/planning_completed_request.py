from __future__ import annotations

# Standard library imports
from typing import Optional

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import MTPlanningCompletedRequestInvalidRunId


class PlanningCompletedRequest(BaseModel):
    """The payload the planning-completed webhook is called with.

    Attributes:
        run_id (str): The planning run that finished.

    Notes:
        The run identifier is all the webhook is told. Everything else — the
        period, the assistants, the quotes — is read from the store, so a
        caller cannot widen what gets emailed by enlarging the payload.
    """

    run_id: str = Field(description="The planning run that finished.")

    @field_validator("run_id", mode="before")
    def validate_run_id(cls, value: Optional[str]) -> str:
        """Validates that ``run_id`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``run_id`` value.

        Returns:
            str: The stripped identifier.

        Raises:
            MTPlanningCompletedRequestInvalidRunId: If ``value`` is not a
                non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTPlanningCompletedRequestInvalidRunId(
                f"Invalid run_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()
