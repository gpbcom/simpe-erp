from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Union

# Third-party imports
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# First-party imports
from models.planning.planning_run.exceptions.suggested_slot_exceptions import (
    MTSuggestedSlotInvalidAssistant,
    MTSuggestedSlotInvalidDay,
    MTSuggestedSlotInvalidMinute,
    MTSuggestedSlotInvalidWindow,
)


class SuggestedSlot(BaseModel):
    """A time somebody qualified is free, offered in place of one that failed.

    Attributes:
        day (date): The day the slot falls on.
        start_minute (int): When it starts, in minutes from midnight.
        end_minute (int): When it ends.
        hca_id (str): The assistant who is free then.
        hca_name (str): The same person, by name.

    Notes:
        - **An offer, not a booking.** Nothing is reserved by producing one of
          these: the slot is free at the moment the planning ran, and the person
          deciding still has to agree it with the customer and re-submit the
          quote. Two operators acting on the same suggestion would both be told
          it fits, and the next planning run is what settles it.
        - That is deliberate. Holding a provisional booking would need an expiry,
          a release path and a screen showing what is held — a reservation
          system, to answer a question an operator resolves in one telephone
          call.
        - The assistant is named because "Tuesday at 14:00" is only useful if
          somebody can be asked whether that works. Which of the offered slots
          is *best* is not decided here either; the agency knows things about its
          own customers that the solver does not.
    """

    model_config = ConfigDict(frozen=True)

    #: The last minute of a day, so a slot cannot run past midnight.
    MAX_MINUTE_OF_DAY: int = 24 * 60

    day: date = Field(description="The day the slot falls on.")
    start_minute: int = Field(description="When it starts, from midnight.")
    end_minute: int = Field(description="When it ends, from midnight.")
    hca_id: str = Field(description="The assistant who is free then.")
    hca_name: str = Field(default="", description="The same person, by name.")

    ############################
    #    Validation Methods    #
    ############################

    @field_validator("day", mode="before")
    def validate_day(cls, value: Union[date, str]) -> date:
        """Validates that the day is a date.

        Args:
            value (Union[date, str]): Raw day, as a date or ISO string.

        Returns:
            date: The validated day.

        Raises:
            MTSuggestedSlotInvalidDay: If it is neither.
        """
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                raise MTSuggestedSlotInvalidDay(
                    f"Invalid day: {value!r}. Must be an ISO date."
                ) from None
        raise MTSuggestedSlotInvalidDay(f"Invalid day: {value!r}. Must be a date.")

    @field_validator("start_minute", "end_minute", mode="before")
    def validate_minute(cls, value: Union[int, str]) -> int:
        """Validates that a minute-of-day falls inside one day.

        Args:
            value (Union[int, str]): Raw minute.

        Returns:
            int: The validated minute.

        Raises:
            MTSuggestedSlotInvalidMinute: If it is not a whole number of
                minutes within a single day.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTSuggestedSlotInvalidMinute(
                f"Invalid minute: {value!r}. Must be a whole number."
            )
        if not 0 <= value <= 24 * 60:
            raise MTSuggestedSlotInvalidMinute(
                f"Invalid minute: {value!r}. Must fall within one day."
            )
        return value

    @field_validator("hca_id", mode="before")
    def validate_hca_id(cls, value: Union[str, None]) -> str:
        """Validates that the slot names who is free.

        Args:
            value (Union[str, None]): Raw identifier.

        Returns:
            str: The identifier.

        Raises:
            MTSuggestedSlotInvalidAssistant: If it is not a non-empty string.

        Notes:
            A slot nobody is attached to cannot be checked with anybody, which
            is the only thing an operator would do with it.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTSuggestedSlotInvalidAssistant(
                f"Invalid hca_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @model_validator(mode="after")
    def check_window(self) -> SuggestedSlot:
        """Ensure the slot runs forwards.

        Returns:
            SuggestedSlot: ``self`` for chaining.

        Raises:
            MTSuggestedSlotInvalidWindow: If it ends at or before it starts.
        """
        if self.end_minute <= self.start_minute:
            raise MTSuggestedSlotInvalidWindow(
                f"Invalid slot: {self.start_minute}-{self.end_minute}. "
                f"Must run forwards."
            )
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def duration_minutes(self) -> int:
        """Return how long the slot is.

        Returns:
            int: The length in minutes.
        """
        return self.end_minute - self.start_minute
