from __future__ import annotations

# Standard library imports
from datetime import date
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator, model_validator

# First-party imports
from models.schemas.exceptions import (
    MTQuoteRescheduleRequestInvalidDay,
    MTQuoteRescheduleRequestInvalidLineId,
    MTQuoteRescheduleRequestInvalidWindow,
)


class QuoteRescheduleRequest(BaseModel):
    """The slot an operator accepted, for one line of a returned quote.

    Attributes:
        MAX_MINUTE_OF_DAY (ClassVar[int]): The last minute of a day, so a
            window cannot run past midnight.
        quote_line_id (str): The line to move.
        day (date): The day the work should happen on instead.
        start_minute (int): Earliest it may begin, in minutes from midnight.
        end_minute (int): Latest it may finish, in the same units.

    Notes:
        - **The shape is the permission.** The payload names a line, a day and
          a window, and nothing else. It cannot carry a status, so accepting a
          new time cannot approve the quote. It cannot carry a price, so
          rescheduling cannot change what is charged — the server reprices from
          the day it lands on.
        - **No assistant.** The offered slot names one, and that is what makes
          the offer worth reading, but a quote records what is sold and when,
          never who does it. Accepting a field here would store a preference the
          planner has no obligation to honour, which is a worse answer than not
          storing it.
        - Minutes from midnight rather than a time, matching
          :class:`~models.planning.planning_run.suggested_slot.SuggestedSlot`.
          The client echoes back the numbers it was offered rather than
          reformatting them into a string somebody has to parse again.
    """

    MAX_MINUTE_OF_DAY: ClassVar[int] = 24 * 60

    quote_line_id: str = Field(description="The line to move.")
    day: date = Field(description="The day the work should happen on instead.")
    start_minute: int = Field(description="Earliest it may begin.")
    end_minute: int = Field(description="Latest it may finish.")

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("quote_line_id", mode="before")
    def validate_quote_line_id(cls, value: Optional[str]) -> str:
        """Validates that ``quote_line_id`` names a line.

        Args:
            value (Optional[str]): Raw ``quote_line_id`` value.

        Returns:
            str: The stripped identifier.

        Raises:
            MTQuoteRescheduleRequestInvalidLineId: If ``value`` is not a
                non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteRescheduleRequestInvalidLineId(
                f"Invalid quote_line_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("day", mode="before")
    def validate_day(cls, value: Union[date, str, None]) -> date:
        """Validates that ``day`` is a date.

        Args:
            value (Union[date, str, None]): Raw ``day`` value.

        Returns:
            date: The day.

        Raises:
            MTQuoteRescheduleRequestInvalidDay: If ``value`` is neither a date
                nor an ISO-8601 date string.
        """
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                raise MTQuoteRescheduleRequestInvalidDay(
                    f"Invalid day: {value!r}. Must be an ISO-8601 date."
                ) from None
        raise MTQuoteRescheduleRequestInvalidDay(
            f"Invalid day: {value!r}. Must be a date."
        )

    @field_validator("start_minute", "end_minute", mode="before")
    def validate_minute(cls, value: Union[int, str, None]) -> int:
        """Validates that a boundary is a minute inside one day.

        Args:
            value (Union[int, str, None]): Raw minute value.

        Returns:
            int: The minute from midnight.

        Raises:
            MTQuoteRescheduleRequestInvalidWindow: If ``value`` is not an
                integer between zero and the end of the day.

        Notes:
            Booleans are refused explicitly. ``True`` is an ``int`` in Python
            and would otherwise be read as one minute past midnight.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTQuoteRescheduleRequestInvalidWindow(
                f"Invalid minute: {value!r}. Must be an integer."
            )
        if value < 0 or value > cls.MAX_MINUTE_OF_DAY:
            raise MTQuoteRescheduleRequestInvalidWindow(
                f"Invalid minute: {value!r}. Must be between 0 and "
                f"{cls.MAX_MINUTE_OF_DAY}."
            )
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    @model_validator(mode="after")
    def check_window(self) -> QuoteRescheduleRequest:
        """Validates that the window runs forwards.

        Returns:
            QuoteRescheduleRequest: The validated payload.

        Raises:
            MTQuoteRescheduleRequestInvalidWindow: If it does not end after it
                starts.

        Notes:
            Whether the window is *wide enough* is not decided here — that
            depends on how long the line takes, which this payload does not
            carry. :meth:`QuoteLine.check_window` refuses a window narrower
            than its own duration, so the rule stays with the thing that knows
            the duration.
        """
        if self.end_minute <= self.start_minute:
            raise MTQuoteRescheduleRequestInvalidWindow(
                f"Invalid window: {self.start_minute}-{self.end_minute}. Must "
                f"end after it starts."
            )
        return self
