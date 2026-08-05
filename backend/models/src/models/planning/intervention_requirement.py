from __future__ import annotations

# Standard library imports
from datetime import date, datetime, time
from typing import ClassVar, Dict, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

# First-party imports
from models.geo.geo_point import GeoPoint
from models.planning.exceptions import (
    MTRequirementInvalidDay,
    MTRequirementInvalidDuration,
    MTRequirementInvalidId,
    MTRequirementInvalidLocation,
    MTRequirementInvalidName,
    MTRequirementInvalidWindow,
)


class InterventionRequirement(BaseModel):
    """One piece of accepted work, waiting to be assigned and timed.

    Attributes:
        MAX_DURATION_MINUTES (ClassVar[int]): Longest single service accepted.
        id (str): Identifier, stable for the duration of one solve.
        quote_line_id (str): The accepted quote line this came from.
        customer_id (str): Whose home the work happens at.
        name (str): What the service is.
        intervention_type_id (str): The catalog entry it sells.
        day (date): The day the work must happen.
        window_start_minute (int): Earliest start, in minutes from midnight.
        window_end_minute (int): Latest finish, in minutes from midnight.
        duration_minutes (int): How long the work takes.
        location (GeoPoint): Where the work happens.

    Notes:
        This is what the solver actually schedules: the quote said *what* and
        *roughly when*, and the solver decides *who* and *exactly when*. The
        window is the customer's constraint; the start inside it is the
        planner's choice.

        Times are minutes from midnight because that is the unit the constraint
        solver works in. Converting once here keeps clock arithmetic out of the
        model that builds the CP-SAT variables.

        ``location`` is a :class:`~models.geo.geo_point.GeoPoint`, not an
        address, so an un-geocoded customer cannot reach the solver at all. The
        requirement builder reports those as unassignable instead, which is a
        far clearer failure than a route computed from a missing coordinate.

        ``name`` and ``intervention_type_id`` are carried through untouched and
        land on the scheduled intervention. The solver never reads them.
    """

    MAX_DURATION_MINUTES: ClassVar[int] = 24 * 60

    id: str = Field(description="Identifier, stable for one solve.")
    quote_line_id: str = Field(description="The accepted quote line this came from.")
    customer_id: str = Field(description="Whose home the work happens at.")
    name: str = Field(description="What the service is.")
    intervention_type_id: str = Field(description="The catalog entry it sells.")
    day: date = Field(description="The day the work must happen.")
    window_start_minute: int = Field(
        description="Earliest start, in minutes from midnight.",
    )
    window_end_minute: int = Field(
        description="Latest finish, in minutes from midnight.",
    )
    duration_minutes: int = Field(description="How long the work takes.")
    location: GeoPoint = Field(description="Where the work happens.")

    @field_validator(
        "id", "quote_line_id", "customer_id", "intervention_type_id", mode="before"
    )
    def validate_identifier(cls, value: Optional[str]) -> str:
        """Validates that an identifier is a non-empty string.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTRequirementInvalidId: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTRequirementInvalidId(
                f"Invalid identifier: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The stripped name.

        Raises:
            MTRequirementInvalidName: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTRequirementInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("day", mode="before")
    def validate_day(cls, value: Union[str, date, datetime, None]) -> Union[str, date]:
        """Validates that ``day`` is a date or an ISO string.

        Args:
            value (Union[str, date, datetime, None]): Raw day value.

        Returns:
            Union[str, date]: The value handed back for Pydantic to parse.

        Raises:
            MTRequirementInvalidDay: If ``value`` is not date-like.
        """
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTRequirementInvalidDay(
            f"Invalid day: {value!r}. Must be a date or an ISO string."
        )

    @field_validator("window_start_minute", "window_end_minute", mode="before")
    def validate_minute_of_day(cls, value: Union[int, str, None]) -> int:
        """Validates that a window bound is a minute within one day.

        Args:
            value (Union[int, str, None]): Raw minute of day.

        Returns:
            int: The validated minute.

        Raises:
            MTRequirementInvalidWindow: If ``value`` is not an integer within
                ``0..1440``.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTRequirementInvalidWindow(
                f"Invalid window bound: {value!r}. "
                f"Must be an integer within 0..{cls.MAX_DURATION_MINUTES}."
            )
        if not 0 <= value <= cls.MAX_DURATION_MINUTES:
            raise MTRequirementInvalidWindow(
                f"Invalid window bound: {value!r}. "
                f"Must be within 0..{cls.MAX_DURATION_MINUTES}."
            )
        return value

    @field_validator("duration_minutes", mode="before")
    def validate_duration_minutes(cls, value: Union[int, str, None]) -> int:
        """Validates that ``duration_minutes`` is a positive whole duration.

        Args:
            value (Union[int, str, None]): Raw duration, in minutes.

        Returns:
            int: The validated duration.

        Raises:
            MTRequirementInvalidDuration: If ``value`` is not a strictly
                positive integer within a day.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTRequirementInvalidDuration(
                f"Invalid duration_minutes: {value!r}. "
                f"Must be a strictly positive integer."
            )
        if not 0 < value <= cls.MAX_DURATION_MINUTES:
            raise MTRequirementInvalidDuration(
                f"Invalid duration_minutes: {value!r}. "
                f"Must be within 1..{cls.MAX_DURATION_MINUTES}."
            )
        return value

    @field_validator("location", mode="before")
    def validate_location(
        cls, value: Union[GeoPoint, Dict[str, JsonValue], None]
    ) -> Union[GeoPoint, Dict[str, JsonValue]]:
        """Validates that ``location`` is a coordinate or a mapping.

        Args:
            value (Union[GeoPoint, Dict[str, JsonValue], None]): Raw location.

        Returns:
            Union[GeoPoint, Dict[str, JsonValue]]: The value handed back for
            Pydantic to build.

        Raises:
            MTRequirementInvalidLocation: If ``value`` is neither a
                :class:`~models.geo.geo_point.GeoPoint` nor a mapping.
        """
        if value is None or not isinstance(value, (GeoPoint, dict)):
            raise MTRequirementInvalidLocation(
                f"Invalid location: {value!r}. Must be a GeoPoint or a mapping."
            )
        return value

    @model_validator(mode="after")
    def check_window(self) -> InterventionRequirement:
        """Ensure the window can contain the work.

        Returns:
            InterventionRequirement: ``self`` for chaining.

        Raises:
            MTRequirementInvalidWindow: If the window does not run forwards, or
                is narrower than the duration.

        Notes:
            An impossible requirement is rejected here rather than handed to
            the solver, which would report it as simply "unassigned" — true,
            but useless for working out why.
        """
        if self.window_end_minute <= self.window_start_minute:
            raise MTRequirementInvalidWindow(
                f"Invalid window: {self.window_start_minute}-"
                f"{self.window_end_minute}. Must run forwards."
            )
        width = self.window_end_minute - self.window_start_minute
        if width < self.duration_minutes:
            raise MTRequirementInvalidWindow(
                f"The window is {width} minutes, which cannot contain a "
                f"{self.duration_minutes}-minute service."
            )
        return self

    def latest_start_minute(self) -> int:
        """Return the last minute the work can begin and still finish in time.

        Returns:
            int: The latest permissible start, in minutes from midnight.

        Notes:
            This is the upper bound of the solver's start variable. Computing
            it here keeps the arithmetic in one place rather than repeated at
            every constraint that needs it.
        """
        return self.window_end_minute - self.duration_minutes

    def window_start_time(self) -> time:
        """Return the window's opening as a wall-clock time.

        Returns:
            time: The earliest start.
        """
        return time(
            hour=self.window_start_minute // 60,
            minute=self.window_start_minute % 60,
        )

    def window_end_time(self) -> time:
        """Return the window's closing as a wall-clock time.

        Returns:
            time: The latest finish.
        """
        return time(
            hour=self.window_end_minute // 60,
            minute=self.window_end_minute % 60,
        )
