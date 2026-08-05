from __future__ import annotations

# Standard library imports
from datetime import time
from typing import ClassVar, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator, model_validator

# First-party imports
from models.configuration.exceptions import (
    MTPlanningConfigInvalidDayEnd,
    MTPlanningConfigInvalidDayStart,
    MTPlanningConfigInvalidLunchBreak,
    MTPlanningConfigInvalidLunchWindow,
    MTPlanningConfigInvalidPenalty,
    MTPlanningConfigInvalidSolverTimeLimit,
    MTPlanningConfigInvalidSpeed,
)


class PlanningConfig(BaseModel):
    """The tunable parameters of the intervention-planning computation.

    Attributes:
        MINUTES_PER_DAY (ClassVar[int]): Number of minutes in a day, the
            exclusive upper bound of every minute-of-day field.
        day_start_minute (int): Earliest minute of the day an intervention may
            start, counted from midnight. Defaults to ``540`` (09:00).
        day_end_minute (int): Latest minute of the day an intervention may end,
            counted from midnight. Defaults to ``1200`` (20:00).
        lunch_break_minutes (int): Minimum uninterrupted lunch break granted to
            every assistant on a working day. Defaults to ``60``.
        lunch_window_start_minute (int): Earliest minute the lunch break may
            start. Defaults to ``690`` (11:30).
        lunch_window_end_minute (int): Latest minute the lunch break may end.
            Defaults to ``870`` (14:30).
        average_speed_kmh (float): Average travel speed assumed for an
            assistant who holds a driving licence. Defaults to ``30.0``.
        average_speed_without_license_kmh (float): Average travel speed assumed
            for an assistant who does not. Defaults to ``12.0``.
        solver_time_limit_seconds (float): Wall-clock budget handed to the
            solver. Defaults to ``30.0``.
        travel_weight (int): Objective weight applied to a minute of travel.
        unassigned_penalty (int): Objective penalty applied to a requirement
            left unassigned.

    Notes:
        - Times are held as minutes from midnight rather than as
          :class:`datetime.time` because that is the unit the constraint solver
          works in. Converting once at the configuration boundary keeps the
          solver free of clock arithmetic; :meth:`day_start_time` and its
          siblings convert back for display.
        - ``unassigned_penalty`` must dominate any realistic travel cost. The
          solver may leave a requirement unassigned rather than fail outright, so
          the penalty is what makes that a last resort instead of a cheap way to
          avoid a long drive.
    """

    MINUTES_PER_DAY: ClassVar[int] = 24 * 60

    day_start_minute: int = Field(
        default=9 * 60,
        description="Earliest start minute of the working day, from midnight.",
    )
    day_end_minute: int = Field(
        default=20 * 60,
        description="Latest end minute of the working day, from midnight.",
    )
    lunch_break_minutes: int = Field(
        default=60,
        description="Minimum uninterrupted lunch break, in minutes.",
    )
    lunch_window_start_minute: int = Field(
        default=11 * 60 + 30,
        description="Earliest minute the lunch break may start, from midnight.",
    )
    lunch_window_end_minute: int = Field(
        default=14 * 60 + 30,
        description="Latest minute the lunch break may end, from midnight.",
    )
    average_speed_kmh: float = Field(
        default=30.0,
        description="Average travel speed with a driving licence, in km/h.",
    )
    average_speed_without_license_kmh: float = Field(
        default=12.0,
        description="Average travel speed without a driving licence, in km/h.",
    )
    solver_time_limit_seconds: float = Field(
        default=30.0,
        description="Wall-clock budget handed to the solver, in seconds.",
    )
    travel_weight: int = Field(
        default=1,
        description="Objective weight applied to one minute of travel.",
    )
    max_intervention_radius_km: float = Field(
        default=30.0,
        description="Default radius seeded into the editable planning settings.",
    )
    unassigned_penalty: int = Field(
        default=100_000,
        description="Objective penalty applied to one unassigned requirement.",
    )

    @field_validator(
        "day_start_minute",
        "day_end_minute",
        "lunch_window_start_minute",
        "lunch_window_end_minute",
        mode="before",
    )
    def validate_minute_of_day(cls, value: Union[int, str]) -> int:
        """Validates that a minute-of-day field is within a single day.

        Args:
            value (Union[int, str]): Raw minute-of-day value.

        Returns:
            int: The validated minute of day.

        Raises:
            MTPlanningConfigInvalidDayStart: If ``value`` is not an integer
                within ``0..1440``.

        Notes:
            One validator covers the four minute-of-day fields because the
            bound is identical for all of them; the ordering between them is
            checked by :meth:`check_bounds`, which can name the specific pair
            that is inconsistent.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTPlanningConfigInvalidDayStart(
                f"Invalid minute of day: {value!r}. "
                f"Must be an integer within 0..{cls.MINUTES_PER_DAY}."
            )
        if not 0 <= value <= cls.MINUTES_PER_DAY:
            raise MTPlanningConfigInvalidDayStart(
                f"Invalid minute of day: {value!r}. "
                f"Must be within 0..{cls.MINUTES_PER_DAY}."
            )
        return value

    @field_validator("lunch_break_minutes", mode="before")
    def validate_lunch_break_minutes(cls, value: Union[int, str]) -> int:
        """Validates that ``lunch_break_minutes`` is a positive duration.

        Args:
            value (Union[int, str]): Raw lunch-break duration, in minutes.

        Returns:
            int: The validated duration.

        Raises:
            MTPlanningConfigInvalidLunchBreak: If ``value`` is not a strictly
                positive integer, or exceeds a full day.

        Notes:
            The business rule sets a floor of one hour, but the value is
            required to be *configurable*, so a shorter break is accepted here
            and the floor is a matter of what gets configured.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTPlanningConfigInvalidLunchBreak(
                f"Invalid lunch_break_minutes: {value!r}. "
                f"Must be a strictly positive integer."
            )
        if value <= 0:
            raise MTPlanningConfigInvalidLunchBreak(
                f"Invalid lunch_break_minutes: {value!r}. Must be strictly positive."
            )
        if value > cls.MINUTES_PER_DAY:
            raise MTPlanningConfigInvalidLunchBreak(
                f"Invalid lunch_break_minutes: {value!r}. "
                f"Must be at most {cls.MINUTES_PER_DAY}."
            )
        return value

    @field_validator(
        "average_speed_kmh",
        "average_speed_without_license_kmh",
        mode="before",
    )
    def validate_speed(cls, value: Union[int, float, str]) -> float:
        """Validates that an average travel speed is strictly positive.

        Args:
            value (Union[int, float, str]): Raw speed value, in km/h.

        Returns:
            float: The validated speed.

        Raises:
            MTPlanningConfigInvalidSpeed: If ``value`` is not a strictly
                positive real number.

        Notes:
            A zero speed would make every travel duration infinite, so it is
            rejected here rather than surfacing as a division error deep inside
            the travel-matrix build.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MTPlanningConfigInvalidSpeed(
                f"Invalid average speed: {value!r}. "
                f"Must be a strictly positive number, in km/h."
            )
        coerced = float(value)
        if coerced <= 0:
            raise MTPlanningConfigInvalidSpeed(
                f"Invalid average speed: {coerced!r}. Must be strictly positive."
            )
        return coerced

    @field_validator("solver_time_limit_seconds", mode="before")
    def validate_solver_time_limit_seconds(cls, value: Union[int, float, str]) -> float:  # noqa: E501
        """Validates that ``solver_time_limit_seconds`` is strictly positive.

        Args:
            value (Union[int, float, str]): Raw time budget, in seconds.

        Returns:
            float: The validated budget.

        Raises:
            MTPlanningConfigInvalidSolverTimeLimit: If ``value`` is not a
                strictly positive real number.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MTPlanningConfigInvalidSolverTimeLimit(
                f"Invalid solver_time_limit_seconds: {value!r}. "
                f"Must be a strictly positive number of seconds."
            )
        coerced = float(value)
        if coerced <= 0:
            raise MTPlanningConfigInvalidSolverTimeLimit(
                f"Invalid solver_time_limit_seconds: {coerced!r}. "
                f"Must be strictly positive."
            )
        return coerced

    @field_validator("travel_weight", "unassigned_penalty", mode="before")
    def validate_objective_term(cls, value: Union[int, str]) -> int:
        """Validates that an objective weight is a non-negative integer.

        Args:
            value (Union[int, str]): Raw weight or penalty value.

        Returns:
            int: The validated value.

        Raises:
            MTPlanningConfigInvalidPenalty: If ``value`` is not a non-negative
                integer.

        Notes:
            Objective terms are integers because the solver's objective is
            integral; a fractional weight would be silently truncated.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTPlanningConfigInvalidPenalty(
                f"Invalid objective term: {value!r}. Must be a non-negative integer."
            )
        if value < 0:
            raise MTPlanningConfigInvalidPenalty(
                f"Invalid objective term: {value!r}. Must be non-negative."
            )
        return value

    @model_validator(mode="after")
    def check_bounds(self) -> PlanningConfig:
        """Ensure the day and lunch windows are internally consistent.

        Returns:
            PlanningConfig: ``self`` for chaining.

        Raises:
            MTPlanningConfigInvalidDayEnd: If the day ends at or before it
                starts.
            MTPlanningConfigInvalidLunchWindow: If the lunch window is empty,
                too short to contain the break, or falls outside the day.
        """
        if self.day_end_minute <= self.day_start_minute:
            raise MTPlanningConfigInvalidDayEnd(
                f"Invalid day_end_minute: {self.day_end_minute}. "
                f"Must be greater than day_start_minute "
                f"({self.day_start_minute})."
            )
        if self.lunch_window_end_minute <= self.lunch_window_start_minute:
            raise MTPlanningConfigInvalidLunchWindow(
                f"Invalid lunch_window_end_minute: {self.lunch_window_end_minute}. "  # noqa: E501
                f"Must be greater than lunch_window_start_minute "
                f"({self.lunch_window_start_minute})."
            )
        if (
            self.lunch_window_start_minute < self.day_start_minute
            or self.lunch_window_end_minute > self.day_end_minute
        ):
            raise MTPlanningConfigInvalidLunchWindow(
                f"Invalid lunch window "
                f"[{self.lunch_window_start_minute}, {self.lunch_window_end_minute}]. "  # noqa: E501
                f"Must fall within the working day "
                f"[{self.day_start_minute}, {self.day_end_minute}]."
            )
        lunch_window_width = (
            self.lunch_window_end_minute - self.lunch_window_start_minute
        )
        if lunch_window_width < self.lunch_break_minutes:
            raise MTPlanningConfigInvalidLunchWindow(
                f"Invalid lunch window width: {lunch_window_width} minutes. "
                f"Must be at least lunch_break_minutes "
                f"({self.lunch_break_minutes})."
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

    def speed_for(self, has_driving_license: bool) -> float:
        """Return the average travel speed to assume for an assistant.

        Args:
            has_driving_license (bool): Whether the assistant holds a licence.

        Returns:
            float: The average speed in km/h.

        Notes:
            An assistant without a licence travels by public transport or on
            foot, so assuming the driving speed for them would produce a route
            they cannot actually keep to.
        """
        if has_driving_license:
            return self.average_speed_kmh
        return self.average_speed_without_license_kmh
