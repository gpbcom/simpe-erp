from __future__ import annotations

# Standard library imports
from typing import Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator, model_validator

# First-party imports
from models.schemas.exceptions import (
    MTPlanningSettingsRequestInvalidDayEnd,
    MTPlanningSettingsRequestInvalidDayStart,
    MTPlanningSettingsRequestInvalidLunchBreak,
    MTPlanningSettingsRequestInvalidLunchWindow,
    MTPlanningSettingsRequestInvalidRadius,
)
from models.settings.planning_settings import PlanningSettings


class PlanningSettingsRequest(BaseModel):
    """The payload changing the planning rules.

    Attributes:
        max_intervention_radius_km (float): How far from home an assistant may
            be sent.
        day_start_minute (int): Earliest minute of the day a visit may start,
            counted from midnight.
        day_end_minute (int): Latest minute of the day a visit may end,
            counted from midnight.
        lunch_break_minutes (int): Length of the uninterrupted midday break.
        lunch_window_start_minute (int): Earliest minute the break may start.
        lunch_window_end_minute (int): Latest minute the break may end.

    Notes:
        - The bounds repeat those on
          :class:`~models.settings.planning_settings.PlanningSettings` rather
          than deferring to them, so a bad payload is refused as a 422 naming the
          field rather than surfacing from deeper in the stack as something
          vaguer. The stored model still enforces them — this is the outer of two
          gates, not a replacement for the inner one.
        - Every field except the radius carries a default matching the stored
          model's. A manager adjusting only the lunch break should not have to
          restate the working day, and a payload that omitted it would otherwise
          be rejected for a field the caller never intended to touch.
    """

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
        default=PlanningSettings.MIN_LUNCH_BREAK_MINUTES,
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

    ############################
    # Fields Validation Methods #
    ############################

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
            MTPlanningSettingsRequestInvalidRadius: If ``value`` is not a
                number within the accepted range.
        """
        if value is None:
            raise MTPlanningSettingsRequestInvalidRadius(
                "Invalid max_intervention_radius_km: a radius is required."
            )
        try:
            radius = float(value)
        except (TypeError, ValueError):
            raise MTPlanningSettingsRequestInvalidRadius(
                f"Invalid max_intervention_radius_km: {value!r}. "  # noqa: E501
                "Must be a number."
            ) from None
        if not (
            PlanningSettings.MIN_RADIUS_KM <= radius <= PlanningSettings.MAX_RADIUS_KM  # noqa: E501
        ):
            raise MTPlanningSettingsRequestInvalidRadius(
                f"Invalid max_intervention_radius_km: {radius!r}. Must be "
                f"between {PlanningSettings.MIN_RADIUS_KM} and "
                f"{PlanningSettings.MAX_RADIUS_KM} km."
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
            MTPlanningSettingsRequestInvalidDayStart: If ``value`` is not a
                whole number within ``0..MINUTES_PER_DAY``.

        Notes:
            Booleans are rejected explicitly: ``True`` is an ``int`` in Python
            and would otherwise be accepted as one minute past midnight.
        """
        if value is None:
            raise MTPlanningSettingsRequestInvalidDayStart(
                "Invalid minute of day: a value is required."
            )
        if isinstance(value, bool):
            raise MTPlanningSettingsRequestInvalidDayStart(
                f"Invalid minute of day: {value!r}. Must be a whole number."
            )
        try:
            minute = int(value)
        except (TypeError, ValueError):
            raise MTPlanningSettingsRequestInvalidDayStart(
                f"Invalid minute of day: {value!r}. Must be a whole number."
            ) from None
        if not 0 <= minute <= PlanningSettings.MINUTES_PER_DAY:
            raise MTPlanningSettingsRequestInvalidDayStart(
                f"Invalid minute of day: {minute!r}. Must be within "
                f"0..{PlanningSettings.MINUTES_PER_DAY}."
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
            MTPlanningSettingsRequestInvalidLunchBreak: If ``value`` is not a
                whole number of minutes at or above the floor.
        """
        if value is None:
            return PlanningSettings.MIN_LUNCH_BREAK_MINUTES
        if isinstance(value, bool):
            raise MTPlanningSettingsRequestInvalidLunchBreak(
                f"Invalid lunch_break_minutes: {value!r}. "  # noqa: E501
                "Must be a whole number."
            )
        try:
            minutes = int(value)
        except (TypeError, ValueError):
            raise MTPlanningSettingsRequestInvalidLunchBreak(
                f"Invalid lunch_break_minutes: {value!r}. "  # noqa: E501
                "Must be a whole number."
            ) from None
        if minutes < PlanningSettings.MIN_LUNCH_BREAK_MINUTES:
            raise MTPlanningSettingsRequestInvalidLunchBreak(
                f"Invalid lunch_break_minutes: {minutes!r}. Must be at least "
                f"{PlanningSettings.MIN_LUNCH_BREAK_MINUTES} minutes."
            )
        return minutes

    @model_validator(mode="after")
    def check_bounds(self) -> PlanningSettingsRequest:
        """Ensure the working day and the lunch window agree with each other.

        Returns:
            PlanningSettingsRequest: ``self`` for chaining.

        Raises:
            MTPlanningSettingsRequestInvalidDayEnd: If the day ends at or
                before it starts.
            MTPlanningSettingsRequestInvalidLunchWindow: If the lunch window is
                empty, falls outside the working day, or is too narrow to hold
                the break.

        Notes:
            Checked here as well as on the stored model so the caller gets a
            422 naming the conflicting pair. Without it the same payload would
            reach the service and fail on the way *into* the database, which
            reads to a manager as the save having broken rather than the
            numbers disagreeing.
        """
        if self.day_end_minute <= self.day_start_minute:
            raise MTPlanningSettingsRequestInvalidDayEnd(
                f"Invalid day_end_minute: {self.day_end_minute}. Must be "
                f"after day_start_minute ({self.day_start_minute})."
            )
        if self.lunch_window_end_minute <= self.lunch_window_start_minute:
            raise MTPlanningSettingsRequestInvalidLunchWindow(
                f"Invalid lunch_window_end_minute: "
                f"{self.lunch_window_end_minute}. Must be after "
                f"lunch_window_start_minute "
                f"({self.lunch_window_start_minute})."
            )
        if (
            self.lunch_window_start_minute < self.day_start_minute
            or self.lunch_window_end_minute > self.day_end_minute
        ):
            raise MTPlanningSettingsRequestInvalidLunchWindow(
                f"Invalid lunch window [{self.lunch_window_start_minute}, "
                f"{self.lunch_window_end_minute}]. Must fall within the "
                f"working day [{self.day_start_minute}, "
                f"{self.day_end_minute}]."
            )
        window_width = self.lunch_window_end_minute - self.lunch_window_start_minute  # noqa: E501
        if window_width < self.lunch_break_minutes:
            raise MTPlanningSettingsRequestInvalidLunchWindow(
                f"Invalid lunch window width: {window_width} minutes. Must be "
                f"at least lunch_break_minutes ({self.lunch_break_minutes})."
            )
        return self
