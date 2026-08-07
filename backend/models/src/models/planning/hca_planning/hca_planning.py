from __future__ import annotations

# Standard library imports
from collections import defaultdict
from datetime import date, datetime
from typing import Dict, List, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

# First-party imports
from models.planning.hca_planning.exceptions import (
    MTPlanningInvalidHcaId,
    MTPlanningInvalidHcaName,
    MTPlanningInvalidInterventions,
    MTPlanningInvalidPeriod,
)
from models.planning.intervention import Intervention


class HcaPlanning(BaseModel):
    """One assistant's diary over a period.

    Attributes:
        hca_id (str): The assistant the diary belongs to.
        hca_full_name (str): Their name.
        period_start (date): First day of the period, inclusive.
        period_end (date): Last day of the period, inclusive.
        interventions (List[Intervention]): The visits, in time order.

    Notes:
        Deliberately per-assistant. An assistant may read only their own
        planning, and a model that could hold several people's visits at once
        would make that a filtering question at every call site rather than a
        property of the object.
    """

    hca_id: str = Field(description="The assistant the diary belongs to.")
    hca_full_name: str = Field(description="The assistant's name.")
    period_start: date = Field(description="First day of the period, inclusive.")
    period_end: date = Field(description="Last day of the period, inclusive.")
    interventions: List[Intervention] = Field(
        default_factory=list,
        description="The visits, in time order.",
    )

    @field_validator("hca_id", mode="before")
    def validate_hca_id(cls, value: Optional[str]) -> str:
        """Validates that ``hca_id`` is a non-empty string.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTPlanningInvalidHcaId: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTPlanningInvalidHcaId(
                f"Invalid hca_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("hca_full_name", mode="before")
    def validate_hca_full_name(cls, value: Optional[str]) -> str:
        """Validates that ``hca_full_name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw name.

        Returns:
            str: The stripped name.

        Raises:
            MTPlanningInvalidHcaName: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTPlanningInvalidHcaName(
                f"Invalid hca_full_name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

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
            MTPlanningInvalidPeriod: If ``value`` is not date-like.
        """
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTPlanningInvalidPeriod(
            f"Invalid period bound: {value!r}. Must be a date or an ISO string."
        )

    @field_validator("interventions", mode="before")
    def validate_interventions(cls, value: JsonValue) -> JsonValue:
        """Validates that ``interventions`` is a list of visits.

        Args:
            value (JsonValue): Raw list of intervention payloads.

        Returns:
            JsonValue: The list handed back for Pydantic to build.

        Raises:
            MTPlanningInvalidInterventions: If ``value`` is neither ``None``
                nor a list, or an entry is neither a mapping nor a built visit.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTPlanningInvalidInterventions(
                f"Invalid interventions: {value!r}. Must be a list or None."
            )
        for entry in value:
            if not isinstance(entry, (Intervention, dict)):
                raise MTPlanningInvalidInterventions(
                    f"Invalid interventions entry: {entry!r}. "
                    f"Must be an Intervention or a mapping."
                )
        return value

    @model_validator(mode="after")
    def check_period(self) -> HcaPlanning:
        """Ensure the period runs forwards.

        Returns:
            HcaPlanning: ``self`` for chaining.

        Raises:
            MTPlanningInvalidPeriod: If ``period_end`` precedes
                ``period_start``.
        """
        if self.period_end < self.period_start:
            raise MTPlanningInvalidPeriod(
                f"Invalid period_end: {self.period_end}. "
                f"Must be on or after period_start ({self.period_start})."
            )
        return self

    def by_day(self) -> Dict[date, List[Intervention]]:
        """Return the visits grouped by day, each in time order.

        Returns:
            Dict[date, List[Intervention]]: The diary, day by day.

        Notes:
            This is the shape a calendar renders from, and the shape an
            assistant reads their round in.
        """
        grouped: Dict[date, List[Intervention]] = defaultdict(list)
        for intervention in self.interventions:
            grouped[intervention.day].append(intervention)
        for visits in grouped.values():
            visits.sort(key=lambda visit: visit.start_time)
        return dict(grouped)

    def overlapping_pairs(self) -> List[tuple[Intervention, Intervention]]:
        """Return every pair of visits that clash.

        Returns:
            List[tuple[Intervention, Intervention]]: The clashing pairs.

        Notes:
            A correct planning has none. This exists so a caller can assert
            that cheaply — an overlap means the assistant is expected to be in
            two homes at once, which is the one error a planning must never
            contain.
        """
        clashes: List[tuple[Intervention, Intervention]] = []
        for visits in self.by_day().values():
            for index, first in enumerate(visits):
                for second in visits[index + 1 :]:
                    if first.occupies(second):
                        clashes.append((first, second))
        return clashes

    def total_minutes(self) -> int:
        """Return how long the assistant is booked for over the period.

        Returns:
            int: The summed duration of every visit, in minutes.
        """
        return sum(visit.duration_minutes() for visit in self.interventions)
