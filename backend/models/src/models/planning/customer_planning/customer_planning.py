from __future__ import annotations

# Standard library imports
from collections import defaultdict
from datetime import date, datetime
from typing import Dict, List, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

# First-party imports
from models.planning.customer_planning.exceptions import (
    MTCustomerPlanningInvalidCustomerId,
    MTCustomerPlanningInvalidCustomerName,
    MTCustomerPlanningInvalidInterventions,
    MTCustomerPlanningInvalidPeriod,
)
from models.planning.intervention import Intervention


class CustomerPlanning(BaseModel):
    """One household's care over a period, as the agency and the household see it.

    Attributes:
        customer_id (str): The household the visits belong to.
        customer_full_name (str): Their name.
        period_start (date): First day of the period, inclusive.
        period_end (date): Last day of the period, inclusive.
        interventions (List[Intervention]): The visits, in time order.

    Notes:
        - **The mirror of
          :class:`~models.planning.hca_planning.hca_planning.HcaPlanning`, on the
          other axis.** An intervention carries both an assistant and a
          household, so the same visits group two ways: by who delivers them,
          which answers "is Monday covered", and by who receives them, which
          answers "what is happening at Madame Vincent's this week". Neither
          question is a filter over the other's answer, which is why there are
          two models rather than one with a mode.
        - **Per household, deliberately.** A model able to hold several
          households at once would make "may this caller see this one" a
          filtering question at every call site instead of a property of the
          object — the same reasoning the assistant's diary is built on, and it
          matters more here: an assistant may read only the households in their
          own portfolio.
        - **This is packaging, not content.** The visits inside come from the one
          query the customer portal also reads
          (``InterventionRepository.list_for_customer``), unchanged and
          unfiltered. What the envelope adds is the household's *name*, which
          the portal has no use for — it already knows whose planning it is —
          and a staff screen listing forty households cannot do without.
        - No ``overlapping_pairs``, unlike the assistant's diary. Two visits at
          once is an error for a person who has to be in both places; a
          household may legitimately have two assistants at the same hour, and a
          method reporting that as a clash would be inventing a rule the agency
          does not have.
    """

    customer_id: str = Field(description="The household the visits belong to.")
    customer_full_name: str = Field(description="The household's name.")
    period_start: date = Field(description="First day of the period, inclusive.")
    period_end: date = Field(description="Last day of the period, inclusive.")
    interventions: List[Intervention] = Field(
        default_factory=list,
        description="The visits, in time order.",
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("customer_id", mode="before")
    def validate_customer_id(cls, value: Optional[str]) -> str:
        """Validates that ``customer_id`` is a non-empty string.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTCustomerPlanningInvalidCustomerId: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCustomerPlanningInvalidCustomerId(
                f"Invalid customer_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("customer_full_name", mode="before")
    def validate_customer_full_name(cls, value: Optional[str]) -> str:
        """Validates that ``customer_full_name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw name.

        Returns:
            str: The stripped name.

        Raises:
            MTCustomerPlanningInvalidCustomerName: If ``value`` is not a
                non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCustomerPlanningInvalidCustomerName(
                f"Invalid customer_full_name: {value!r}. Must be a non-empty string."
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
            MTCustomerPlanningInvalidPeriod: If ``value`` is not date-like.
        """
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTCustomerPlanningInvalidPeriod(
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
            MTCustomerPlanningInvalidInterventions: If ``value`` is neither
                ``None`` nor a list, or an entry is neither a mapping nor a
                built visit.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTCustomerPlanningInvalidInterventions(
                f"Invalid interventions: {value!r}. Must be a list or None."
            )
        for entry in value:
            if not isinstance(entry, (Intervention, dict)):
                raise MTCustomerPlanningInvalidInterventions(
                    f"Invalid interventions entry: {entry!r}. "
                    f"Must be an Intervention or a mapping."
                )
        return value

    @model_validator(mode="after")
    def check_period(self) -> CustomerPlanning:
        """Ensure the period runs forwards.

        Returns:
            CustomerPlanning: ``self`` for chaining.

        Raises:
            MTCustomerPlanningInvalidPeriod: If ``period_end`` precedes
                ``period_start``.
        """
        if self.period_end < self.period_start:
            raise MTCustomerPlanningInvalidPeriod(
                f"Invalid period_end: {self.period_end}. "
                f"Must be on or after period_start ({self.period_start})."
            )
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def by_day(self) -> Dict[date, List[Intervention]]:
        """Return the visits grouped by day, each in time order.

        Returns:
            Dict[date, List[Intervention]]: The care received, day by day.

        Notes:
            The shape a calendar renders from, and the shape a family reads
            their week in.
        """
        grouped: Dict[date, List[Intervention]] = defaultdict(list)
        for intervention in self.interventions:
            grouped[intervention.day].append(intervention)
        for visits in grouped.values():
            visits.sort(key=lambda visit: visit.start_time)
        return dict(grouped)

    def total_minutes(self) -> int:
        """Return how much care the household receives over the period.

        Returns:
            int: The summed duration of every visit, in minutes.
        """
        return sum(visit.duration_minutes() for visit in self.interventions)

    def assistants(self) -> List[str]:
        """Return the assistants who come to this household, each once.

        Returns:
            List[str]: Their names, alphabetically.

        Notes:
            Answers the question a family actually rings about — "who is coming
            this week" — from the names already copied onto each visit, so it
            needs no second read and survives an assistant leaving the agency.
        """
        return sorted({visit.hca_full_name for visit in self.interventions})
