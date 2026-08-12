from __future__ import annotations

# Standard library imports
from datetime import date, datetime, time
from typing import Dict, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

# First-party imports
from models.enums import InterventionStatus
from models.geo.postal_address import PostalAddress
from models.planning.intervention.exceptions import (
    MTInterventionInvalidAddress,
    MTInterventionInvalidDay,
    MTInterventionInvalidId,
    MTInterventionInvalidName,
    MTInterventionInvalidStatus,
    MTInterventionInvalidTeamId,
    MTInterventionInvalidTime,
)


class Intervention(BaseModel):
    """One scheduled visit: who, what, where and exactly when.

    Attributes:
        id (Optional[str]): Identifier, populated on read from the store.
        planning_run_id (Optional[str]): The run that produced this visit.
        company_id (str): The agency whose calendar this visit sits on.
        team_id (str): The team whose half of that calendar it sits on.
        name (str): What the service is, as written on the quote.
        intervention_type_id (str): The catalog entry it sells.
        quote_line_id (str): The accepted quote line it delivers.
        hca_id (str): The assistant who performs it.
        hca_full_name (str): Their name, copied so a planning reads as a diary.
        customer_id (str): The customer it is for.
        day (date): The day it happens.
        start_time (time): When it begins.
        end_time (time): When it ends.
        address (PostalAddress): Where it happens.
        status (InterventionStatus): Where it is in its lifecycle.

    Notes:
        The assistant's name and the customer's address are **copies** taken
        when the visit was planned. A planning is a document an assistant works
        from; re-resolving it against live records would make a printed round
        disagree with the screen after any edit.

        The times are exact, unlike the quote line's window. Deciding them is
        what the planning computation does.
    """

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    planning_run_id: Optional[str] = Field(
        default=None,
        description="The run that produced this visit.",
    )
    company_id: str = Field(description="The agency whose calendar this visit sits on.")
    team_id: str = Field(description="The team that delivers this visit.")
    name: str = Field(description="What the service is.")
    intervention_type_id: str = Field(description="The catalog entry it sells.")
    quote_line_id: str = Field(description="The accepted quote line it delivers.")
    hca_id: str = Field(description="The assistant who performs it.")
    hca_full_name: str = Field(description="The assistant's name.")
    customer_id: str = Field(description="The customer it is for.")
    day: date = Field(description="The day it happens.")
    start_time: time = Field(description="When it begins.")
    end_time: time = Field(description="When it ends.")
    address: PostalAddress = Field(description="Where it happens.")
    status: InterventionStatus = Field(
        default=InterventionStatus.PLANNED,
        description="Where it is in its lifecycle.",
    )

    @field_validator("id", "planning_run_id", mode="before")
    def validate_optional_identifier(cls, value: Optional[str]) -> Optional[str]:
        """Validates that an optional identifier is ``None`` or non-empty.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            Optional[str]: The stripped identifier, or ``None``.

        Raises:
            MTInterventionInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTInterventionInvalidId(
                f"Invalid identifier: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator(
        "company_id",
        "intervention_type_id",
        "quote_line_id",
        "hca_id",
        "customer_id",
        mode="before",
    )
    def validate_identifier(cls, value: Optional[str]) -> str:
        """Validates that a required identifier is a non-empty string.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTInterventionInvalidId: If ``value`` is not a non-empty string.

        Notes:
            ``company_id`` and ``team_id`` are here rather than beside
            ``planning_run_id`` deliberately. A visit is deleted in bulk by the
            agency, the team and the period it belongs to, so a visit missing
            either would escape the replacement for ever or be swept up by
            another team's run — which is why both are required, like the
            assistant and the customer, and not optional like the run that
            happens to have produced it.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTInterventionInvalidId(
                f"Invalid identifier: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("team_id", mode="before")
    def validate_team_id(cls, value: Optional[str]) -> str:
        """Validates that ``team_id`` names the team delivering the visit.

        Args:
            value (Optional[str]): Raw ``team_id`` value.

        Returns:
            str: The stripped identifier.

        Raises:
            MTInterventionInvalidTeamId: If ``value`` is not a non-empty string.

        Notes:
            Its own validator rather than a member of the grouped identifier
            check beside it, because the failure it describes is a different
            one. A missing catalogue entry or customer makes a visit
            *incomplete*; a missing team makes it **unreplaceable** — the delete
            that rewrites a period is scoped by ``(company, team, day)``, so a
            visit naming no team escapes every re-plan for ever.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTInterventionInvalidTeamId(
                f"Invalid team_id: {value!r}. Must be a non-empty string naming "
                f"the team that delivers this visit."
            )
        return value.strip()

    @field_validator("name", "hca_full_name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that a display name is a non-empty string.

        Args:
            value (Optional[str]): Raw name.

        Returns:
            str: The stripped name.

        Raises:
            MTInterventionInvalidName: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTInterventionInvalidName(
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
            MTInterventionInvalidDay: If ``value`` is not date-like.
        """
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTInterventionInvalidDay(
            f"Invalid day: {value!r}. Must be a date or an ISO string."
        )

    @field_validator("start_time", "end_time", mode="before")
    def validate_clock_time(cls, value: Union[str, time, None]) -> Union[str, time]:
        """Validates that a clock time is a time or an ISO string.

        Args:
            value (Union[str, time, None]): Raw time value.

        Returns:
            Union[str, time]: The value handed back for Pydantic to parse.

        Raises:
            MTInterventionInvalidTime: If ``value`` is not time-like.
        """
        if isinstance(value, (str, time)):
            return value
        raise MTInterventionInvalidTime(
            f"Invalid time: {value!r}. Must be a time or an ISO string."
        )

    @field_validator("address", mode="before")
    def validate_address(
        cls, value: Union[PostalAddress, Dict[str, JsonValue], None]
    ) -> Union[PostalAddress, Dict[str, JsonValue]]:
        """Validates that ``address`` is an address or a mapping.

        Args:
            value (Union[PostalAddress, Dict[str, JsonValue], None]): Raw
                address value.

        Returns:
            Union[PostalAddress, Dict[str, JsonValue]]: The value handed back
            for Pydantic to build.

        Raises:
            MTInterventionInvalidAddress: If ``value`` is neither a
                :class:`~models.geo.postal_address.PostalAddress` nor a
                mapping.
        """
        if value is None or not isinstance(value, (PostalAddress, dict)):
            raise MTInterventionInvalidAddress(
                f"Invalid address: {value!r}. Must be a PostalAddress or a mapping."
            )
        return value

    @field_validator("status", mode="before")
    def validate_status(
        cls, value: Union[str, InterventionStatus, None]
    ) -> InterventionStatus:
        """Validates that ``status`` is a known intervention status.

        Args:
            value (Union[str, InterventionStatus, None]): Raw status. ``None``
                falls back to :attr:`InterventionStatus.PLANNED`.

        Returns:
            InterventionStatus: The coerced status.

        Raises:
            MTInterventionInvalidStatus: If ``value`` is not a known status.
        """
        if value is None:
            return InterventionStatus.PLANNED
        if isinstance(value, InterventionStatus):
            return value
        try:
            return InterventionStatus(value)
        except ValueError:
            raise MTInterventionInvalidStatus(
                f"Invalid status: {value!r}. Must be one of: "
                f"{', '.join(InterventionStatus.values())}."
            ) from None

    @model_validator(mode="after")
    def check_times(self) -> Intervention:
        """Ensure the visit ends after it starts.

        Returns:
            Intervention: ``self`` for chaining.

        Raises:
            MTInterventionInvalidTime: If ``end_time`` is not after
                ``start_time``.

        Notes:
            A zero-length or reversed visit would occupy no time in the
            assistant's day, so the overlap checks that keep a planning
            coherent would silently let another visit sit on top of it.
        """
        if self.end_time <= self.start_time:
            raise MTInterventionInvalidTime(
                f"Invalid end_time: {self.end_time}. "
                f"Must be after start_time ({self.start_time})."
            )
        return self

    def duration_minutes(self) -> int:
        """Return how long the visit lasts.

        Returns:
            int: The duration in minutes.
        """
        start = self.start_time.hour * 60 + self.start_time.minute
        end = self.end_time.hour * 60 + self.end_time.minute
        return end - start

    def occupies(self, other: Intervention) -> bool:
        """Return whether this visit overlaps another on the same day.

        Args:
            other (Intervention): The visit to compare against.

        Returns:
            bool: ``True`` when both fall on the same day and their times
            overlap.

        Notes:
            Touching visits do not overlap: one ending at 11:00 and the next
            starting at 11:00 is a back-to-back round, which is exactly what
            the planner tries to produce.
        """
        if self.day != other.day:
            return False
        return self.start_time < other.end_time and other.start_time < self.end_time
