from __future__ import annotations

# Standard library imports
from datetime import date, datetime, time
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator, model_validator

# First-party imports
from models.enums import AvailabilityKind
from models.people.hca.exceptions import (
    MTAvailabilitySlotInvalidEndDate,
    MTAvailabilitySlotInvalidEndTime,
    MTAvailabilitySlotInvalidHcaId,
    MTAvailabilitySlotInvalidId,
    MTAvailabilitySlotInvalidKind,
    MTAvailabilitySlotInvalidNote,
    MTAvailabilitySlotInvalidStartDate,
    MTAvailabilitySlotInvalidStartTime,
)


class AvailabilitySlot(BaseModel):
    """A period during which a Home Care Assistant cannot be scheduled.

    Attributes:
        id (Optional[str]): Identifier, populated on read from the store.
        hca_id (str): Identifier of the assistant the slot belongs to.
        start_date (date): First day of the period, inclusive.
        end_date (date): Last day of the period, inclusive.
        kind (AvailabilityKind): Why the assistant is unavailable.
        start_time (Optional[time]): Start of the blocked window on each day,
            or ``None`` for a whole-day block.
        end_time (Optional[time]): End of the blocked window on each day, or
            ``None`` for a whole-day block.
        note (Optional[str]): Free-text note.

    Notes:
        - The model records **un**availability, not availability. Assistants are
          assumed full-time, so a working day is the default and only the
          exceptions are stored — which keeps the table proportional to the
          number of absences rather than to the number of days.
        - ``end_date`` is inclusive. A single day off is one slot whose start and
          end are the same date, not a zero-width range.
        - Both times are set or neither is. A half-open window would be ambiguous
          about which side of the day is blocked; :meth:`is_whole_day` relies on
          that invariant, which :meth:`check_period` enforces.
    """

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    hca_id: str = Field(description="Identifier of the assistant the slot belongs to.")
    start_date: date = Field(description="First day of the period, inclusive.")
    end_date: date = Field(description="Last day of the period, inclusive.")
    kind: AvailabilityKind = Field(description="Why the assistant is unavailable.")
    start_time: Optional[time] = Field(
        default=None,
        description="Start of the blocked window on each day, or None.",
    )
    end_time: Optional[time] = Field(
        default=None,
        description="End of the blocked window on each day, or None.",
    )
    note: Optional[str] = Field(default=None, description="Free-text note.")

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``id`` value.

        Returns:
            Optional[str]: The identifier, or ``None`` before it is persisted.

        Raises:
            MTAvailabilitySlotInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTAvailabilitySlotInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("hca_id", mode="before")
    def validate_hca_id(cls, value: Optional[str]) -> str:
        """Validates that ``hca_id`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``hca_id`` value.

        Returns:
            str: The stripped assistant identifier.

        Raises:
            MTAvailabilitySlotInvalidHcaId: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTAvailabilitySlotInvalidHcaId(
                f"Invalid hca_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("start_date", mode="before")
    def validate_start_date(
        cls, value: Union[str, date, datetime, None]
    ) -> Union[str, date]:
        """Validates that ``start_date`` is a date or an ISO string.

        Args:
            value (Union[str, date, datetime, None]): Raw ``start_date`` value.

        Returns:
            Union[str, date]: The value handed back for Pydantic to parse.

        Raises:
            MTAvailabilitySlotInvalidStartDate: If ``value`` is not a date-like
                value.
        """
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTAvailabilitySlotInvalidStartDate(
            f"Invalid start_date: {value!r}. Must be a date or an ISO-8601 string."
        )

    @field_validator("end_date", mode="before")
    def validate_end_date(
        cls, value: Union[str, date, datetime, None]
    ) -> Union[str, date]:
        """Validates that ``end_date`` is a date or an ISO string.

        Args:
            value (Union[str, date, datetime, None]): Raw ``end_date`` value.

        Returns:
            Union[str, date]: The value handed back for Pydantic to parse.

        Raises:
            MTAvailabilitySlotInvalidEndDate: If ``value`` is not a date-like
                value.
        """
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTAvailabilitySlotInvalidEndDate(
            f"Invalid end_date: {value!r}. Must be a date or an ISO-8601 string."
        )

    @field_validator("kind", mode="before")
    def validate_kind(
        cls, value: Union[str, AvailabilityKind, None]
    ) -> AvailabilityKind:
        """Validates that ``kind`` is a known availability kind.

        Args:
            value (Union[str, AvailabilityKind, None]): Raw ``kind`` value.

        Returns:
            AvailabilityKind: The coerced kind.

        Raises:
            MTAvailabilitySlotInvalidKind: If ``value`` is not one of the known
                availability kinds.
        """
        if isinstance(value, AvailabilityKind):
            return value
        try:
            return AvailabilityKind(value)
        except ValueError:
            raise MTAvailabilitySlotInvalidKind(
                f"Invalid kind: {value!r}. Must be one of: "
                f"{', '.join(AvailabilityKind.values())}."
            ) from None

    @field_validator("start_time", mode="before")
    def validate_start_time(
        cls, value: Union[str, time, None]
    ) -> Union[str, time, None]:
        """Validates that ``start_time`` is a time, an ISO string or ``None``.

        Args:
            value (Union[str, time, None]): Raw ``start_time`` value.

        Returns:
            Union[str, time, None]: The value handed back for Pydantic to parse.

        Raises:
            MTAvailabilitySlotInvalidStartTime: If ``value`` is neither
                ``None`` nor a time-like value.
        """
        if value is None:
            return None
        if isinstance(value, (str, time)):
            return value
        raise MTAvailabilitySlotInvalidStartTime(
            f"Invalid start_time: {value!r}. "
            f"Must be a time, an ISO-8601 string, or None."
        )

    @field_validator("end_time", mode="before")
    def validate_end_time(cls, value: Union[str, time, None]) -> Union[str, time, None]:
        """Validates that ``end_time`` is a time, an ISO string or ``None``.

        Args:
            value (Union[str, time, None]): Raw ``end_time`` value.

        Returns:
            Union[str, time, None]: The value handed back for Pydantic to parse.

        Raises:
            MTAvailabilitySlotInvalidEndTime: If ``value`` is neither ``None``
                nor a time-like value.
        """
        if value is None:
            return None
        if isinstance(value, (str, time)):
            return value
        raise MTAvailabilitySlotInvalidEndTime(
            f"Invalid end_time: {value!r}. Must be a time, an ISO-8601 string, or None."
        )

    @field_validator("note", mode="before")
    def validate_note(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``note`` is ``None`` or a string.

        Args:
            value (Optional[str]): Raw ``note`` value.

        Returns:
            Optional[str]: The stripped note, or ``None`` when blank.

        Raises:
            MTAvailabilitySlotInvalidNote: If ``value`` is neither ``None`` nor
                a string.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTAvailabilitySlotInvalidNote(
                f"Invalid note: {value!r}. Must be a string or None."
            )
        stripped = value.strip()
        return stripped if stripped else None

    @model_validator(mode="after")
    def check_period(self) -> AvailabilitySlot:
        """Ensure the date range and the optional time window are coherent.

        Returns:
            AvailabilitySlot: ``self`` for chaining.

        Raises:
            MTAvailabilitySlotInvalidEndDate: If ``end_date`` falls before
                ``start_date``.
            MTAvailabilitySlotInvalidEndTime: If only one of the two times is
                supplied, or if ``end_time`` is not strictly after
                ``start_time``.
        """
        if self.end_date < self.start_date:
            raise MTAvailabilitySlotInvalidEndDate(
                f"Invalid end_date: {self.end_date}. "
                f"Must be on or after start_date ({self.start_date})."
            )
        if (self.start_time is None) != (self.end_time is None):
            raise MTAvailabilitySlotInvalidEndTime(
                "Invalid time window: start_time and end_time must both be set "
                "for a partial-day slot, or both be None for a whole-day slot."
            )
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise MTAvailabilitySlotInvalidEndTime(
                f"Invalid end_time: {self.end_time}. "
                f"Must be strictly after start_time ({self.start_time})."
            )
        return self

    def is_whole_day(self) -> bool:
        """Return whether the slot blocks the entire day.

        Returns:
            bool: ``True`` when no time window is set.

        Notes:
            A whole-day slot removes the assistant from that day entirely; a
            partial one only carves a window out of it.
        """
        return self.start_time is None

    def covers(self, day: date) -> bool:
        """Return whether the slot applies to a given day.

        Args:
            day (date): The day to test.

        Returns:
            bool: ``True`` when ``day`` falls within the inclusive range.
        """
        return self.start_date <= day <= self.end_date
