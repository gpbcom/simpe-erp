from __future__ import annotations

# Standard library imports
from typing import Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import (
    MTPlanningSettingsRequestInvalidLunchBreak,
    MTPlanningSettingsRequestInvalidRadius,
)
from models.settings.planning_settings import PlanningSettings


class PlanningSettingsRequest(BaseModel):
    """The payload changing the planning rules.

    Attributes:
        max_intervention_radius_km (float): How far from home an assistant may
            be sent.
        lunch_break_minutes (int): Length of the uninterrupted midday break.

    Notes:
        The bounds repeat those on
        :class:`~models.settings.planning_settings.PlanningSettings` rather
        than deferring to them, so a bad payload is refused as a 422 naming the
        field rather than surfacing from deeper in the stack as something
        vaguer. The stored model still enforces them — this is the outer of two
        gates, not a replacement for the inner one.
    """

    max_intervention_radius_km: float = Field(
        description="How far from home an assistant may be sent, in kilometres."
    )
    lunch_break_minutes: int = Field(
        default=PlanningSettings.MIN_LUNCH_BREAK_MINUTES,
        description="Length of the uninterrupted midday break, in minutes.",
    )

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
        except TypeError, ValueError:
            raise MTPlanningSettingsRequestInvalidRadius(
                f"Invalid max_intervention_radius_km: {value!r}. Must be a number."
            ) from None
        if not (
            PlanningSettings.MIN_RADIUS_KM <= radius <= PlanningSettings.MAX_RADIUS_KM
        ):
            raise MTPlanningSettingsRequestInvalidRadius(
                f"Invalid max_intervention_radius_km: {radius!r}. Must be "
                f"between {PlanningSettings.MIN_RADIUS_KM} and "
                f"{PlanningSettings.MAX_RADIUS_KM} km."
            )
        return radius

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
                f"Invalid lunch_break_minutes: {value!r}. Must be a whole number."
            )
        try:
            minutes = int(value)
        except TypeError, ValueError:
            raise MTPlanningSettingsRequestInvalidLunchBreak(
                f"Invalid lunch_break_minutes: {value!r}. Must be a whole number."
            ) from None
        if minutes < PlanningSettings.MIN_LUNCH_BREAK_MINUTES:
            raise MTPlanningSettingsRequestInvalidLunchBreak(
                f"Invalid lunch_break_minutes: {minutes!r}. Must be at least "
                f"{PlanningSettings.MIN_LUNCH_BREAK_MINUTES} minutes."
            )
        return minutes
