from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.settings.exceptions import (
    MTPlanningSettingsInvalidDate,
    MTPlanningSettingsInvalidId,
    MTPlanningSettingsInvalidLunchBreak,
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
        id (str): Identifier; always :attr:`SINGLETON_ID`.
        max_intervention_radius_km (float): How far from their own home an
            assistant may be sent.
        lunch_break_minutes (int): How long the uninterrupted midday break is.
        updated_by (Optional[str]): The account that last changed these.
        updated_at (Optional[datetime]): When they were last changed.

    Notes:
        These live in the database rather than in ``app.yaml`` because the
        specification puts them in the hands of an administrator or a manager.
        A YAML value would need a deployment to change, which is not what
        "configurable by a manager" means.

        The configuration file still carries defaults. They seed the row the
        first time it is read, so a fresh install plans sensibly before anybody
        has visited the settings screen.

        **One row, fixed identifier.** These are agency-wide rules, not a
        per-anything collection, and a table that can hold two rows invites the
        question of which one the solver used.

        The radius is bounded at both ends deliberately. Zero would place
        nothing at all and read as "the planner is broken"; an unbounded value
        would silently turn the constraint off, which is the failure that looks
        like success.
    """

    SINGLETON_ID: ClassVar[str] = "planning-settings"
    MIN_RADIUS_KM: ClassVar[float] = 0.1
    MAX_RADIUS_KM: ClassVar[float] = 500.0
    MIN_LUNCH_BREAK_MINUTES: ClassVar[int] = 60

    id: str = Field(
        default=SINGLETON_ID, description="Identifier of the single settings row."
    )
    max_intervention_radius_km: float = Field(
        description="How far from home an assistant may be sent, in kilometres."
    )
    lunch_break_minutes: int = Field(
        default=MIN_LUNCH_BREAK_MINUTES,
        description="Length of the uninterrupted midday break, in minutes.",
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
    def validate_id(cls, value: Union[str, None]) -> str:
        """Validates that ``id`` names the singleton row.

        Args:
            value (Union[str, None]): Raw ``id`` value.

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
    def validate_updated_by(cls, value: Union[str, None]) -> Optional[str]:
        """Validates that the editing account, when given, is identified.

        Args:
            value (Union[str, None]): Raw ``updated_by`` value.

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

    ############################
    # Publicly Exposed Methods #
    ############################

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
