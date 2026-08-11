from __future__ import annotations

# Standard library imports
from datetime import datetime, time
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator, model_validator

# First-party imports
from models.settings.exceptions import (
    MTPlanningSettingsInvalidDate,
    MTPlanningSettingsInvalidDayEnd,
    MTPlanningSettingsInvalidDayStart,
    MTPlanningSettingsInvalidId,
    MTPlanningSettingsInvalidLunchBreak,
    MTPlanningSettingsInvalidLunchWindow,
    MTPlanningSettingsInvalidRadius,
    MTPlanningSettingsInvalidUpdatedBy,
)


class PlanningSettings(BaseModel):
    """The planning rules an administrator or manager may change at runtime.

    Attributes:
        SINGLETON_ID (ClassVar[str]): The identifier of the one settings row.
        MIN_RADIUS_KM (ClassVar[float]): Smallest radius that can place any
            work at all.
        MAX_RADIUS_KM (ClassVar[float]): Largest radius accepted, guarding
            against a value that disables the constraint by accident.
        MIN_LUNCH_BREAK_MINUTES (ClassVar[int]): The contractual floor.
        MINUTES_PER_DAY (ClassVar[int]): Minutes in a day, the inclusive upper
            bound of every minute-of-day field.
        id (str): Identifier; always :attr:`SINGLETON_ID`.
        max_intervention_radius_km (float): How far from their own home an
            assistant may be sent.
        day_start_minute (int): Earliest minute of the day a visit may start,
            counted from midnight.
        day_end_minute (int): Latest minute of the day a visit may end,
            counted from midnight.
        lunch_break_minutes (int): How long the uninterrupted midday break is.
        lunch_window_start_minute (int): Earliest minute the break may start.
        lunch_window_end_minute (int): Latest minute the break may end.
        updated_by (Optional[str]): The account that last changed these.
        updated_at (Optional[datetime]): When they were last changed.

    Notes:
        - These live in the database rather than in ``app.yaml`` because the
          specification puts them in the hands of an administrator or a manager.
          A YAML value would need a deployment to change, which is not what
          "configurable by a manager" means.
        - **The working day and the lunch window are here for the same reason
          the break length is.** They were configuration-file values, which made
          "we now start at 08:00" a deployment rather than a decision. The
          solver reads all six from this row, so the day it plans is the day a
          manager last agreed to.
        - Times are minutes from midnight, not :class:`datetime.time`, because
          that is the unit the constraint solver works in. Converting once at
          this boundary keeps the solver free of clock arithmetic;
          :meth:`day_start_time` and :meth:`day_end_time` convert back for
          display.
        - The configuration file still carries defaults. They seed the row the
          first time it is read, so a fresh install plans sensibly before anybody
          has visited the settings screen.
        - **One row, fixed identifier.** These are agency-wide rules, not a
          per-anything collection, and a table that can hold two rows invites the
          question of which one the solver used.
        - The radius is bounded at both ends deliberately. Zero would place
          nothing at all and read as "the planner is broken"; an unbounded value
          would silently turn the constraint off, which is the failure that looks
          like success.
    """

    SINGLETON_ID: ClassVar[str] = "planning-settings"
    MIN_RADIUS_KM: ClassVar[float] = 0.1
    MAX_RADIUS_KM: ClassVar[float] = 500.0
    MIN_LUNCH_BREAK_MINUTES: ClassVar[int] = 60
    MINUTES_PER_DAY: ClassVar[int] = 24 * 60

    id: str = Field(
        default=SINGLETON_ID, description="Identifier of the single settings row."
    )
    max_intervention_radius_km: float = Field(
        description="How far from home an assistant may be sent, in kilometres."
    )
    day_start_minute: int = Field(
        default=9 * 60,
        description="Earliest start minute of the working day, from midnight.",
    )
    day_end_minute: int = Field(
        default=20 * 60,
        description="Latest end minute of the working day, from midnight.",
    )
    lunch_break_minutes: int = Field(
        default=MIN_LUNCH_BREAK_MINUTES,
        description="Length of the uninterrupted midday break, in minutes.",
    )
    lunch_window_start_minute: int = Field(
        default=11 * 60 + 30,
        description="Earliest minute the lunch break may start, from midnight.",
    )
    lunch_window_end_minute: int = Field(
        default=14 * 60 + 30,
        description="Latest minute the lunch break may end, from midnight.",
    )
    updated_by: Optional[str] = Field(
        default=None, description="The account that last changed these settings."
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="When they were last changed."
    )

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> str:
        """Validates that ``id`` names the singleton row.

        Args:
            value (Optional[str]): Raw ``id`` value.

        Returns:
            str: The identifier.

        Raises:
            MTPlanningSettingsInvalidId: If ``value`` is not the singleton
                identifier.

        Notes:
            Refusing any other value is what keeps the table to one row even if
            a caller invents an identifier: there is nowhere else for a second
            set of rules to live.
        """
        if value is None:
            return cls.SINGLETON_ID
        if not isinstance(value, str) or value.strip() != cls.SINGLETON_ID:
            raise MTPlanningSettingsInvalidId(
                f"Invalid id: {value!r}. The planning settings are a single "
                f"row and must be identified as {cls.SINGLETON_ID!r}."
            )
        return cls.SINGLETON_ID

    @field_validator("max_intervention_radius_km", mode="before")
    def validate_max_intervention_radius_km(
        cls, value: Union[float, int, str, None]
    ) -> float:
        """Validates that the radius is a usable distance.

        Args:
            value (Union[float, int, str, None]): Raw radius value.

        Returns:
            float: The radius in kilometres.

        Raises:
            MTPlanningSettingsInvalidRadius: If ``value`` is not a number
                between :attr:`MIN_RADIUS_KM` and :attr:`MAX_RADIUS_KM`.

        Notes:
            A radius of zero is rejected rather than read as "no limit". The
            two readings are opposite, and guessing wrong either strands every
            assistant at home or sends them across the country.
        """
        if value is None:
            raise MTPlanningSettingsInvalidRadius(
                "Invalid max_intervention_radius_km: a radius is required."
            )
        try:
            radius = float(value)
        except (TypeError, ValueError):
            raise MTPlanningSettingsInvalidRadius(
                f"Invalid max_intervention_radius_km: {value!r}. Must be a number."
            ) from None
        if not cls.MIN_RADIUS_KM <= radius <= cls.MAX_RADIUS_KM:
            raise MTPlanningSettingsInvalidRadius(
                f"Invalid max_intervention_radius_km: {radius!r}. Must be "
                f"between {cls.MIN_RADIUS_KM} and {cls.MAX_RADIUS_KM} km."
            )
        return radius

    @field_validator(
        "day_start_minute",
        "day_end_minute",
        "lunch_window_start_minute",
        "lunch_window_end_minute",
        mode="before",
    )
    def validate_minute_of_day(cls, value: Union[int, str, None]) -> int:
        """Validates that a minute-of-day field falls within a single day.

        Args:
            value (Union[int, str, None]): Raw minute-of-day value.

        Returns:
            int: The validated minute of day.

        Raises:
            MTPlanningSettingsInvalidDayStart: If ``value`` is not a whole
                number within ``0..MINUTES_PER_DAY``.

        Notes:
            - One validator covers all four because the bound is identical for
              each of them. The ordering *between* them is checked by
              :meth:`check_bounds`, which can name the pair that disagrees —
              something a per-field validator cannot see.
            - Booleans are rejected explicitly. ``True`` is an ``int`` in Python
              and would otherwise be accepted as one minute past midnight.
        """
        if value is None:
            raise MTPlanningSettingsInvalidDayStart(
                "Invalid minute of day: a value is required."
            )
        if isinstance(value, bool):
            raise MTPlanningSettingsInvalidDayStart(
                f"Invalid minute of day: {value!r}. Must be a whole number."
            )
        try:
            minute = int(value)
        except (TypeError, ValueError):
            raise MTPlanningSettingsInvalidDayStart(
                f"Invalid minute of day: {value!r}. Must be a whole number."
            ) from None
        if not 0 <= minute <= cls.MINUTES_PER_DAY:
            raise MTPlanningSettingsInvalidDayStart(
                f"Invalid minute of day: {minute!r}. Must be within "
                f"0..{cls.MINUTES_PER_DAY}."
            )
        return minute

    @field_validator("lunch_break_minutes", mode="before")
    def validate_lunch_break_minutes(cls, value: Union[int, str, None]) -> int:
        """Validates that the lunch break meets the contractual floor.

        Args:
            value (Union[int, str, None]): Raw lunch-break value.

        Returns:
            int: The break length in minutes.

        Raises:
            MTPlanningSettingsInvalidLunchBreak: If ``value`` is not a whole
                number of minutes of at least
                :attr:`MIN_LUNCH_BREAK_MINUTES`.

        Notes:
            The floor is enforced here rather than left to whoever edits the
            settings. A break shortened below an hour is not a preference, it
            is a plan that breaches the agreement it was built from.
        """
        if value is None:
            return cls.MIN_LUNCH_BREAK_MINUTES
        if isinstance(value, bool):
            raise MTPlanningSettingsInvalidLunchBreak(
                f"Invalid lunch_break_minutes: {value!r}. Must be a whole "
                f"number of minutes."
            )
        try:
            minutes = int(value)
        except (TypeError, ValueError):
            raise MTPlanningSettingsInvalidLunchBreak(
                f"Invalid lunch_break_minutes: {value!r}. Must be a whole "
                f"number of minutes."
            ) from None
        if minutes < cls.MIN_LUNCH_BREAK_MINUTES:
            raise MTPlanningSettingsInvalidLunchBreak(
                f"Invalid lunch_break_minutes: {minutes!r}. Must be at least "
                f"{cls.MIN_LUNCH_BREAK_MINUTES} minutes."
            )
        return minutes

    @field_validator("updated_by", mode="before")
    def validate_updated_by(cls, value: Optional[str]) -> Optional[str]:
        """Validates that the editing account, when given, is identified.

        Args:
            value (Optional[str]): Raw ``updated_by`` value.

        Returns:
            Optional[str]: The account identifier, or ``None``.

        Raises:
            MTPlanningSettingsInvalidUpdatedBy: If ``value`` is neither
                ``None`` nor a non-empty string.

        Notes:
            Optional because the seeded defaults were nobody's decision. Once
            somebody edits them, the record of who did is not optional — a
            radius that quietly halved is a question with a name attached.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTPlanningSettingsInvalidUpdatedBy(
                f"Invalid updated_by: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("updated_at", mode="before")
    def validate_updated_at(
        cls, value: Union[datetime, str, None]
    ) -> Optional[datetime]:
        """Validates that ``updated_at`` is a datetime.

        Args:
            value (Union[datetime, str, None]): Raw timestamp value.

        Returns:
            Optional[datetime]: The timestamp, or ``None``.

        Raises:
            MTPlanningSettingsInvalidDate: If ``value`` is neither ``None`` nor
                a datetime or ISO-8601 string.
        """
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                raise MTPlanningSettingsInvalidDate(
                    f"Invalid updated_at: {value!r}. Must be an ISO-8601 datetime."
                ) from None
        raise MTPlanningSettingsInvalidDate(
            f"Invalid updated_at: {value!r}. Must be a datetime."
        )

    @model_validator(mode="after")
    def check_bounds(self) -> PlanningSettings:
        """Ensure the working day and the lunch window agree with each other.

        Returns:
            PlanningSettings: ``self`` for chaining.

        Raises:
            MTPlanningSettingsInvalidDayEnd: If the day ends at or before it
                starts.
            MTPlanningSettingsInvalidLunchWindow: If the lunch window is
                empty, falls outside the working day, or is too narrow to hold
                the break.

        Notes:
            **This is what stops a manager saving a day nobody can work.** The
            four values are individually plausible and only wrong in
            combination: a 12:00–13:00 lunch window with a 90 minute break is
            two settings that each look fine and together make every day
            infeasible. Caught here, it is a 422 naming the conflict; caught
            by the solver, it is a planning run that fails at midnight with
            "no feasible slot" against every visit.
        """
        if self.day_end_minute <= self.day_start_minute:
            raise MTPlanningSettingsInvalidDayEnd(
                f"Invalid day_end_minute: {self.day_end_minute}. Must be "
                f"after day_start_minute ({self.day_start_minute})."
            )
        if self.lunch_window_end_minute <= self.lunch_window_start_minute:
            raise MTPlanningSettingsInvalidLunchWindow(
                f"Invalid lunch_window_end_minute: "
                f"{self.lunch_window_end_minute}. Must be after "
                f"lunch_window_start_minute "
                f"({self.lunch_window_start_minute})."
            )
        if (
            self.lunch_window_start_minute < self.day_start_minute
            or self.lunch_window_end_minute > self.day_end_minute
        ):
            raise MTPlanningSettingsInvalidLunchWindow(
                f"Invalid lunch window [{self.lunch_window_start_minute}, "
                f"{self.lunch_window_end_minute}]. Must fall within the "
                f"working day [{self.day_start_minute}, "
                f"{self.day_end_minute}]."
            )
        window_width = self.lunch_window_end_minute - self.lunch_window_start_minute
        if window_width < self.lunch_break_minutes:
            raise MTPlanningSettingsInvalidLunchWindow(
                f"Invalid lunch window width: {window_width} minutes. Must be "
                f"at least lunch_break_minutes ({self.lunch_break_minutes})."
            )
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def day_start_time(self) -> time:
        """Return the start of the working day as a wall-clock time.

        Returns:
            time: The time of day the working day starts at.
        """
        return time(
            hour=self.day_start_minute // 60,
            minute=self.day_start_minute % 60,
        )

    def day_end_time(self) -> time:
        """Return the end of the working day as a wall-clock time.

        Returns:
            time: The time of day the working day ends at.
        """
        return time(
            hour=self.day_end_minute // 60,
            minute=self.day_end_minute % 60,
        )

    def describe_working_day(self) -> str:
        """Return the working day as a human-readable range.

        Returns:
            str: The range, such as ``"09:00–20:00"``.

        Notes:
            Used in the unplaced-work report, which a manager reads to decide
            what to change. It prints the minute as well as the hour: a day
            ending at 19:30 reported as "19:00" would send somebody looking
            for a half-hour that was never there.
        """
        return (
            f"{self.day_start_time().strftime('%H:%M')}–"
            f"{self.day_end_time().strftime('%H:%M')}"
        )

    def covers(self, distance_km: float) -> bool:
        """Return whether a journey of this length is within the radius.

        Args:
            distance_km (float): The straight-line distance from an assistant's
                home to the work.

        Returns:
            bool: ``True`` when the work is close enough to be assigned.

        Notes:
            Inclusive at the boundary. A visit exactly at the limit is inside
            it — excluding it would make a round-numbered radius behave one
            metre tighter than the number an administrator typed.
        """
        return distance_km <= self.max_intervention_radius_km
