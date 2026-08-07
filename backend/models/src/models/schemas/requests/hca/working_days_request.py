from __future__ import annotations

# Standard library imports
from typing import List

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator

# First-party imports
from models.enums import Weekday
from models.schemas.exceptions import MTWorkingDaysRequestInvalidWeekdays


class WorkingDaysRequest(BaseModel):
    """The payload declaring which days of the week an assistant works.

    Attributes:
        working_weekdays (List[Weekday]): The days worked, at least one.

    Notes:
        - The assistant is named by the path, never by this payload. An
          assistant filing against a colleague's identifier would take that
          colleague off their rounds, so the owning assistant is the one the
          route addresses and the service refuses if that is not the caller.
        - The whole week is sent, not a day to add or remove. A partial payload
          would need the caller and the server to agree on what the current set
          is, and two tabs open on the same screen would then race: last-write
          wins on a whole week is a week somebody chose, on a delta it is a week
          nobody did.
    """

    working_weekdays: List[Weekday] = Field(
        description="The days of the week the assistant works at all."
    )

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("working_weekdays", mode="before")
    def validate_working_weekdays(cls, value: JsonValue) -> List[Weekday]:
        """Validates that the payload names at least one known weekday.

        Args:
            value (JsonValue): Raw list of weekday values.

        Returns:
            List[Weekday]: The days worked, deduplicated and ordered Monday
            first.

        Raises:
            MTWorkingDaysRequestInvalidWeekdays: If ``value`` is not a
                non-empty list of known weekdays.

        Notes:
            An empty list is a 422 rather than a silent reset to the standard
            week. Clearing every box is a statement — and the two ways to read
            it, "I work no days" and "put me back on the default", are
            opposites.
        """
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise MTWorkingDaysRequestInvalidWeekdays(
                f"Invalid working_weekdays: {value!r}. Must be a list of weekdays."
            )
        days: List[Weekday] = []
        for entry in value:
            if isinstance(entry, Weekday):
                days.append(entry)
                continue
            try:
                days.append(Weekday(entry))
            except ValueError:
                raise MTWorkingDaysRequestInvalidWeekdays(
                    f"Invalid working_weekdays entry: {entry!r}. Must be one "
                    f"of: {', '.join(Weekday.values())}."
                ) from None
        if not days:
            raise MTWorkingDaysRequestInvalidWeekdays(
                "Invalid working_weekdays: at least one day must be worked."
            )
        return sorted(set(days), key=lambda day: day.iso_weekday())
