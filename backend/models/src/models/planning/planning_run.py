from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from typing import List, Optional, Union

# Third-party imports
from pydantic import (
    BaseModel,
    Field,
    JsonValue,
    field_serializer,
    field_validator,
    model_validator,
)

# First-party imports
from models.enums import PlanningRunStatus
from models.planning.exceptions import (
    MTPlanningRunInvalidCount,
    MTPlanningRunInvalidDate,
    MTPlanningRunInvalidError,
    MTPlanningRunInvalidId,
    MTPlanningRunInvalidPeriod,
    MTPlanningRunInvalidStatus,
    MTPlanningRunInvalidUnassigned,
)


class PlanningRun(BaseModel):
    """One execution of the planning computation.

    Attributes:
        id (Optional[str]): Identifier, populated on read from the store.
        status (PlanningRunStatus): Where the run is.
        requested_by (str): The administrator who started it.
        period_start (date): First day planned, inclusive.
        period_end (date): Last day planned, inclusive.
        started_at (Optional[datetime]): When the solver began.
        finished_at (Optional[datetime]): When it stopped.
        total_travel_minutes (Optional[int]): Travel time in the solution.
        scheduled_count (Optional[int]): How many requirements were placed.
        unassigned_requirement_ids (List[str]): What could not be placed.
        error_message (Optional[str]): Why the run failed, when it did.

    Notes:
        The run is a record, not a lock. It exists so a caller who asked for a
        planning can poll for the answer: the solve is CPU-bound and runs in a
        worker thread, so the request that started it returns immediately.

        ``unassigned_requirement_ids`` is the honest part of the result. The
        solver is allowed to leave work unplaced rather than fail, so a
        succeeded run with a non-empty list means "here is a plan, and here is
        what would not fit" — which is far more useful than no plan at all.
    """

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    status: PlanningRunStatus = Field(
        default=PlanningRunStatus.PENDING,
        description="Where the run is.",
    )
    requested_by: str = Field(description="The administrator who started it.")
    period_start: date = Field(description="First day planned, inclusive.")
    period_end: date = Field(description="Last day planned, inclusive.")
    started_at: Optional[datetime] = Field(
        default=None,
        description="When the solver began.",
    )
    finished_at: Optional[datetime] = Field(
        default=None,
        description="When it stopped.",
    )
    total_travel_minutes: Optional[int] = Field(
        default=None,
        description="Travel time in the solution.",
    )
    scheduled_count: Optional[int] = Field(
        default=None,
        description="How many requirements were placed.",
    )
    unassigned_requirement_ids: List[str] = Field(
        default_factory=list,
        description="What could not be placed.",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Why the run failed, when it did.",
    )

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            Optional[str]: The identifier, or ``None``.

        Raises:
            MTPlanningRunInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTPlanningRunInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("requested_by", mode="before")
    def validate_requested_by(cls, value: Optional[str]) -> str:
        """Validates that ``requested_by`` is a non-empty string.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTPlanningRunInvalidId: If ``value`` is not a non-empty string.

        Notes:
            Always recorded. A planning run rewrites everybody's calendar, so
            who asked for it is part of the answer.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTPlanningRunInvalidId(
                f"Invalid requested_by: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("status", mode="before")
    def validate_status(
        cls, value: Union[str, PlanningRunStatus, None]
    ) -> PlanningRunStatus:
        """Validates that ``status`` is a known run status.

        Args:
            value (Union[str, PlanningRunStatus, None]): Raw status. ``None``
                falls back to :attr:`PlanningRunStatus.PENDING`.

        Returns:
            PlanningRunStatus: The coerced status.

        Raises:
            MTPlanningRunInvalidStatus: If ``value`` is not a known status.
        """
        if value is None:
            return PlanningRunStatus.PENDING
        if isinstance(value, PlanningRunStatus):
            return value
        try:
            return PlanningRunStatus(value)
        except ValueError:
            raise MTPlanningRunInvalidStatus(
                f"Invalid status: {value!r}. Must be one of: "
                f"{', '.join(PlanningRunStatus.values())}."
            ) from None

    @field_validator("period_start", "period_end", mode="before")
    def validate_period_bound(
        cls, value: Union[str, date, datetime, None]
    ) -> Union[str, date]:
        """Validates that a period bound is a date or an ISO string.

        Args:
            value (Union[str, date, datetime, None]): Raw date value.

        Returns:
            Union[str, date]: The value handed back for Pydantic to parse.

        Raises:
            MTPlanningRunInvalidPeriod: If ``value`` is not date-like.
        """
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTPlanningRunInvalidPeriod(
            f"Invalid period bound: {value!r}. Must be a date or an ISO string."
        )

    @field_validator("started_at", "finished_at", mode="before")
    def validate_timestamp(
        cls, value: Union[str, datetime, None]
    ) -> Union[str, datetime, None]:
        """Validates that a timestamp is datetime-like or ``None``.

        Args:
            value (Union[str, datetime, None]): Raw timestamp.

        Returns:
            Union[str, datetime, None]: The value handed back for Pydantic.

        Raises:
            MTPlanningRunInvalidDate: If ``value`` is neither ``None`` nor
                datetime-like.
        """
        if value is None or isinstance(value, (str, datetime)):
            return value
        raise MTPlanningRunInvalidDate(
            f"Invalid timestamp: {value!r}. Must be a datetime, an ISO string, or None."
        )

    @field_validator("total_travel_minutes", "scheduled_count", mode="before")
    def validate_count(cls, value: Union[int, str, None]) -> Optional[int]:
        """Validates that a count is ``None`` or a non-negative integer.

        Args:
            value (Union[int, str, None]): Raw count.

        Returns:
            Optional[int]: The validated count, or ``None`` before the run
            finishes.

        Raises:
            MTPlanningRunInvalidCount: If ``value`` is neither ``None`` nor a
                non-negative integer.
        """
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTPlanningRunInvalidCount(
                f"Invalid count: {value!r}. Must be a non-negative integer or None."
            )
        if value < 0:
            raise MTPlanningRunInvalidCount(
                f"Invalid count: {value!r}. Must be non-negative."
            )
        return value

    @field_validator("unassigned_requirement_ids", mode="before")
    def validate_unassigned(cls, value: JsonValue) -> List[str]:
        """Validates that the unassigned list holds identifiers.

        Args:
            value (JsonValue): Raw list of requirement identifiers.

        Returns:
            List[str]: The stripped identifiers.

        Raises:
            MTPlanningRunInvalidUnassigned: If ``value`` is neither ``None``
                nor a list, or an entry is not a non-empty string.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTPlanningRunInvalidUnassigned(
                f"Invalid unassigned_requirement_ids: {value!r}. "
                f"Must be a list or None."
            )
        validated: List[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise MTPlanningRunInvalidUnassigned(
                    f"Invalid unassigned id: {entry!r}. Must be a non-empty string."
                )
            validated.append(entry.strip())
        return validated

    @field_validator("error_message", mode="before")
    def validate_error_message(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``error_message`` is ``None`` or a string.

        Args:
            value (Optional[str]): Raw message.

        Returns:
            Optional[str]: The stripped message, or ``None`` when blank.

        Raises:
            MTPlanningRunInvalidError: If ``value`` is neither ``None`` nor a
                string.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTPlanningRunInvalidError(
                f"Invalid error_message: {value!r}. Must be a string or None."
            )
        stripped = value.strip()
        return stripped if stripped else None

    @model_validator(mode="after")
    def check_period(self) -> PlanningRun:
        """Ensure the planned period runs forwards.

        Returns:
            PlanningRun: ``self`` for chaining.

        Raises:
            MTPlanningRunInvalidPeriod: If ``period_end`` precedes
                ``period_start``.
        """
        if self.period_end < self.period_start:
            raise MTPlanningRunInvalidPeriod(
                f"Invalid period_end: {self.period_end}. "
                f"Must be on or after period_start ({self.period_start})."
            )
        return self

    @field_serializer("started_at", "finished_at")
    def serialize_timestamp(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize a timestamp to an ISO-8601 string.

        Args:
            value (Optional[datetime]): The timestamp to serialize.

        Returns:
            Optional[str]: The ISO-8601 representation, or ``None``.
        """
        return value.isoformat() if value is not None else None

    def is_terminal(self) -> bool:
        """Return whether the run has finished, one way or the other.

        Returns:
            bool: ``True`` once the run succeeded or failed.

        Notes:
            Clients poll until this is true.
        """
        return self.status.is_terminal()

    def is_complete(self) -> bool:
        """Return whether every requirement was placed.

        Returns:
            bool: ``True`` when the run succeeded and nothing was left over.
        """
        return (
            self.status is PlanningRunStatus.SUCCEEDED
            and not self.unassigned_requirement_ids
        )
