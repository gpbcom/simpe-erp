from __future__ import annotations

# Standard library imports
from typing import Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import MTEmailDispatchResponseInvalidCount


class EmailDispatchResponse(BaseModel):
    """What the planning-completed webhook delivered.

    Attributes:
        run_id (str): The planning run the dispatch was for.
        plannings_sent (int): How many assistants received their diary.
        quotes_sent (int): How many customers received their quote.

    Notes:
        Counts rather than a bare acknowledgement. A webhook that answers
        "accepted" tells an operator nothing; one that answers "0 of 14
        plannings" tells them the mailbox credentials expired, without anyone
        having to open a log.
    """

    run_id: str = Field(description="The planning run the dispatch was for.")
    plannings_sent: int = Field(
        description="How many assistants received their diary.",
    )
    quotes_sent: int = Field(
        description="How many customers received their quote.",
    )

    @field_validator("plannings_sent", "quotes_sent", mode="before")
    def validate_counts(cls, value: Union[int, float, None]) -> int:
        """Validates that a count is a non-negative integer.

        Args:
            value (Union[int, float, None]): Raw count.

        Returns:
            int: The validated count.

        Raises:
            MTEmailDispatchResponseInvalidCount: If ``value`` is not a
                non-negative integer.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTEmailDispatchResponseInvalidCount(
                f"Invalid count: {value!r}. Must be a non-negative integer."
            )
        if value < 0:
            raise MTEmailDispatchResponseInvalidCount(
                f"Invalid count: {value!r}. Must not be negative."
            )
        return value
