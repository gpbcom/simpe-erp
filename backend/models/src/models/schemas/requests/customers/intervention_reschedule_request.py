from __future__ import annotations

# Standard library imports
from datetime import date
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, model_validator

# First-party imports
from models.schemas.exceptions import (
    MTInterventionRescheduleRequestInvalidDay,
    MTInterventionRescheduleRequestInvalidWindow,
)


class InterventionRescheduleRequest(BaseModel):
    """When a household would rather a visit happened.

    Attributes:
        MAX_MINUTE_OF_DAY (ClassVar[int]): The last minute of a day, so a
            window cannot run past midnight.
        day (date): The day the visit should happen on instead.
        start_minute (int): Earliest it may begin, in minutes from midnight.
        end_minute (int): Latest it may finish, in the same units.

    Notes:
        - **The visit is in the path, not the payload.** The route is
          ``POST /portal/interventions/{id}/reschedule`` and the visit already
          names the quote line it delivers, so a ``quote_line_id`` here would be
          a second answer to "which piece of work" — and one a household has no
          way to know. Compare
          :class:`~models.schemas.requests.quoting.quote_reschedule_request.QuoteRescheduleRequest`,
          which *does* carry it, because a manager rescheduling from the quote
          screen is holding the line and not a visit.
        - **A window, not a time.** The household says when they are available;
          the solver decides where inside that the visit lands, against the
          assistant's round and their travel. Accepting an exact time would be
          a promise the planner cannot keep, and the visit would come back
          unplaced with nothing explaining why.
        - Minutes from midnight rather than ``HH:MM``, matching every other
          time on the wire — it is the unit the solver works in, and the screens
          convert at the edge.
        - Nothing here says *whether* the work still happens. Cancelling is a
          separate route with a separate consequence, and folding the two
          together would let a mistyped window quietly remove a visit.
    """

    MAX_MINUTE_OF_DAY: ClassVar[int] = 24 * 60

    day: date = Field(description="The day the visit should happen on instead.")
    start_minute: int = Field(description="Earliest it may begin.")
    end_minute: int = Field(description="Latest it may finish.")

    #############################
    # Fields Validation Methods #
    #############################

    @model_validator(mode="before")
    @classmethod
    def validate_payload(
        cls, values: Union[dict, "InterventionRescheduleRequest"]
    ) -> Union[dict, "InterventionRescheduleRequest"]:
        """Validates the day and the window together.

        Args:
            values (Union[dict, InterventionRescheduleRequest]): Raw payload.

        Returns:
            Union[dict, InterventionRescheduleRequest]: The payload, unchanged.

        Raises:
            MTInterventionRescheduleRequestInvalidDay: If the day is missing.
            MTInterventionRescheduleRequestInvalidWindow: If either bound is
                outside the day, or the window is empty.

        Notes:
            Validated as a pair rather than field by field, because the rule
            that matters is a relationship: an ``end_minute`` at or before the
            ``start_minute`` is not a narrow window but no window at all, and
            neither bound is wrong on its own.
        """
        if not isinstance(values, dict):
            return values
        if values.get("day") in (None, ""):
            raise MTInterventionRescheduleRequestInvalidDay(
                "Invalid day: a reschedule must name the day it moves to."
            )
        start: Optional[int] = values.get("start_minute")
        end: Optional[int] = values.get("end_minute")
        if not isinstance(start, int) or isinstance(start, bool):
            raise MTInterventionRescheduleRequestInvalidWindow(
                f"Invalid start_minute: {start!r}. Must be minutes from midnight."
            )
        if not isinstance(end, int) or isinstance(end, bool):
            raise MTInterventionRescheduleRequestInvalidWindow(
                f"Invalid end_minute: {end!r}. Must be minutes from midnight."
            )
        if not 0 <= start < cls.MAX_MINUTE_OF_DAY:
            raise MTInterventionRescheduleRequestInvalidWindow(
                f"Invalid start_minute: {start}. Must fall inside the day."
            )
        if not 0 < end <= cls.MAX_MINUTE_OF_DAY:
            raise MTInterventionRescheduleRequestInvalidWindow(
                f"Invalid end_minute: {end}. Must fall inside the day."
            )
        if end <= start:
            raise MTInterventionRescheduleRequestInvalidWindow(
                f"Invalid window: {start}–{end}. The end must fall after the "
                f"start, or there is no time to place the visit in."
            )
        return values
