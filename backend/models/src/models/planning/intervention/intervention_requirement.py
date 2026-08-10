from __future__ import annotations

# Standard library imports
from datetime import date, datetime, time
from typing import ClassVar, Dict, List, Optional, Union

# Third-party imports
from pydantic import (
    BaseModel,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

# First-party imports
from models.geo.geo_point import GeoPoint
from models.planning.intervention.exceptions import (
    MTRequirementInvalidDay,
    MTRequirementInvalidDuration,
    MTRequirementInvalidId,
    MTRequirementInvalidLocation,
    MTRequirementInvalidName,
    MTRequirementInvalidRequiredCertifications,
    MTRequirementInvalidRequiredSkills,
    MTRequirementInvalidWindow,
)


class InterventionRequirement(BaseModel):
    """One piece of accepted work, waiting to be assigned and timed.

    Attributes:
        MAX_DURATION_MINUTES (ClassVar[int]): Longest single service accepted.
        id (str): Identifier, stable for the duration of one solve.
        quote_line_id (str): The accepted quote line this came from.
        quote_reference (str): The quote's human-readable reference. Carried
            so that a visit which cannot be placed can be reported against the
            document an operator actually has in front of them, rather than
            against an identifier that appears on no screen.
        customer_name (str): Who the work is for, for the same reason.
        customer_id (str): Whose home the work happens at.
        name (str): What the service is.
        intervention_type_id (str): The catalog entry it sells.
        day (date): The day the work must happen.
        window_start_minute (int): Earliest start, in minutes from midnight.
        window_end_minute (int): Latest finish, in minutes from midnight.
        duration_minutes (int): How long the work takes.
        location (GeoPoint): Where the work happens.
        required_certification_codes (List[str]): Certification codes the
            assistant taking this work must hold, already resolved from the
            quote line and its catalog entry.
        required_skill_codes (List[str]): Skill codes the assistant taking this
            work must declare, resolved the same way.

    Notes:
        - This is what the solver actually schedules: the quote said *what* and
          *roughly when*, and the solver decides *who* and *exactly when*. The
          window is the customer's constraint; the start inside it is the
          planner's choice.
        - Times are minutes from midnight because that is the unit the constraint
          solver works in. Converting once here keeps clock arithmetic out of the
          model that builds the CP-SAT variables.
        - ``location`` is a :class:`~models.geo.geo_point.GeoPoint`, not an
          address, so an un-geocoded customer cannot reach the solver at all. The
          requirement builder reports those as unassignable instead, which is a
          far clearer failure than a route computed from a missing coordinate.
        - ``name`` and ``intervention_type_id`` are carried through untouched and
          land on the scheduled intervention. The solver never reads them.
        - ``required_certification_codes`` arrives **already resolved** — the
          requirement builder has applied the line's override or fallen back to
          the catalog entry — so the solver never has to hold a second lookup
          table or know that the inheritance rule exists. Building the
          requirement is where the quote stops being paperwork and becomes work,
          and the qualification a piece of work needs is a property of the work.
        - ``required_skill_codes`` arrives resolved the same way and is kept
          **separate** all the way into the solver. Both become the same kind
          of hard constraint, so merging them would produce an identical plan —
          what it would cost is the diagnosis: a run that places nothing has to
          be able to say whether the answer is to hire somebody or to ask an
          assistant to finish filling in their profile.
    """

    MAX_DURATION_MINUTES: ClassVar[int] = 24 * 60

    id: str = Field(description="Identifier, stable for one solve.")
    quote_line_id: str = Field(description="The accepted quote line this came from.")
    quote_reference: str = Field(
        default="",
        description="Human-readable reference of the quote it was sold on.",
    )
    customer_name: str = Field(
        default="",
        description="Who the work is for, for a message somebody has to read.",
    )
    customer_id: str = Field(description="Whose home the work happens at.")
    name: str = Field(description="What the service is.")
    intervention_type_id: str = Field(description="The catalog entry it sells.")
    day: date = Field(description="The day the work must happen.")
    window_start_minute: int = Field(
        description="Earliest start, in minutes from midnight.",
    )
    window_end_minute: int = Field(
        description="Latest finish, in minutes from midnight.",
    )
    duration_minutes: int = Field(description="How long the work takes.")
    location: GeoPoint = Field(description="Where the work happens.")
    required_certification_codes: List[str] = Field(
        default_factory=list,
        description="Certification codes the assistant taking this must hold.",
    )
    required_skill_codes: List[str] = Field(
        default_factory=list,
        description="Skill codes the assistant taking this must declare.",
    )

    @field_validator(
        "id", "quote_line_id", "customer_id", "intervention_type_id", mode="before"
    )
    def validate_identifier(cls, value: Optional[str]) -> str:
        """Validates that an identifier is a non-empty string.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTRequirementInvalidId: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTRequirementInvalidId(
                f"Invalid identifier: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The stripped name.

        Raises:
            MTRequirementInvalidName: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTRequirementInvalidName(
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
            MTRequirementInvalidDay: If ``value`` is not date-like.
        """
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTRequirementInvalidDay(
            f"Invalid day: {value!r}. Must be a date or an ISO string."
        )

    @field_validator("window_start_minute", "window_end_minute", mode="before")
    def validate_minute_of_day(cls, value: Union[int, str, None]) -> int:
        """Validates that a window bound is a minute within one day.

        Args:
            value (Union[int, str, None]): Raw minute of day.

        Returns:
            int: The validated minute.

        Raises:
            MTRequirementInvalidWindow: If ``value`` is not an integer within
                ``0..1440``.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTRequirementInvalidWindow(
                f"Invalid window bound: {value!r}. "
                f"Must be an integer within 0..{cls.MAX_DURATION_MINUTES}."
            )
        if not 0 <= value <= cls.MAX_DURATION_MINUTES:
            raise MTRequirementInvalidWindow(
                f"Invalid window bound: {value!r}. "
                f"Must be within 0..{cls.MAX_DURATION_MINUTES}."
            )
        return value

    @field_validator("duration_minutes", mode="before")
    def validate_duration_minutes(cls, value: Union[int, str, None]) -> int:
        """Validates that ``duration_minutes`` is a positive whole duration.

        Args:
            value (Union[int, str, None]): Raw duration, in minutes.

        Returns:
            int: The validated duration.

        Raises:
            MTRequirementInvalidDuration: If ``value`` is not a strictly
                positive integer within a day.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTRequirementInvalidDuration(
                f"Invalid duration_minutes: {value!r}. "
                f"Must be a strictly positive integer."
            )
        if not 0 < value <= cls.MAX_DURATION_MINUTES:
            raise MTRequirementInvalidDuration(
                f"Invalid duration_minutes: {value!r}. "
                f"Must be within 1..{cls.MAX_DURATION_MINUTES}."
            )
        return value

    @field_validator("location", mode="before")
    def validate_location(
        cls, value: Union[GeoPoint, Dict[str, JsonValue], None]
    ) -> Union[GeoPoint, Dict[str, JsonValue]]:
        """Validates that ``location`` is a coordinate or a mapping.

        Args:
            value (Union[GeoPoint, Dict[str, JsonValue], None]): Raw location.

        Returns:
            Union[GeoPoint, Dict[str, JsonValue]]: The value handed back for
            Pydantic to build.

        Raises:
            MTRequirementInvalidLocation: If ``value`` is neither a
                :class:`~models.geo.geo_point.GeoPoint` nor a mapping.
        """
        if value is None or not isinstance(value, (GeoPoint, dict)):
            raise MTRequirementInvalidLocation(
                f"Invalid location: {value!r}. Must be a GeoPoint or a mapping."
            )
        return value

    @field_validator("required_certification_codes", mode="before")
    def validate_required_certification_codes(cls, value: JsonValue) -> List[str]:  # noqa: E501
        """Validates that the required codes are a list of catalog keys.

        Args:
            value (JsonValue): Raw ``required_certification_codes`` value.
                ``None`` falls back to an empty list.

        Returns:
            List[str]: The upper-cased codes, de-duplicated.

        Raises:
            MTRequirementInvalidRequiredCertifications: If ``value`` is neither
                ``None`` nor a list of non-empty strings.

        Notes:
            Normalised again here even though the builder hands over codes that
            are already upper-cased. A requirement is also built directly in
            tests and could be built by a future caller, and a code that
            reached the solver in the wrong case would match nobody and fail
            the run with a reason that looks like a staffing problem.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTRequirementInvalidRequiredCertifications(
                f"Invalid required_certification_codes: {value!r}. "
                f"Must be a list of certification codes."
            )
        codes: List[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise MTRequirementInvalidRequiredCertifications(
                    f"Invalid certification code: {entry!r}. "
                    f"Must be a non-empty string."
                )
            normalized = entry.strip().upper()
            if normalized not in codes:
                codes.append(normalized)
        return codes

    @field_validator("required_skill_codes", mode="before")
    def validate_required_skill_codes(cls, value: JsonValue) -> List[str]:
        """Validates that the required skill codes are a list of catalog keys.

        Args:
            value (JsonValue): Raw ``required_skill_codes`` value. ``None``
                falls back to an empty list.

        Returns:
            List[str]: The upper-cased codes, de-duplicated.

        Raises:
            MTRequirementInvalidRequiredSkills: If ``value`` is neither ``None``
                nor a list of non-empty strings.

        Notes:
            Normalised again here even though the builder hands over codes that
            are already upper-cased, for the same reason as the certification
            list: a requirement is also built directly in tests, and a code that
            reached the solver in the wrong case would match nobody and fail the
            run with a reason that looks like a staffing problem.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTRequirementInvalidRequiredSkills(
                f"Invalid required_skill_codes: {value!r}. "
                f"Must be a list of skill codes."
            )
        codes: List[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise MTRequirementInvalidRequiredSkills(
                    f"Invalid skill code: {entry!r}. Must be a non-empty string."
                )
            normalized = entry.strip().upper()
            if normalized not in codes:
                codes.append(normalized)
        return codes

    @model_validator(mode="after")
    def check_window(self) -> InterventionRequirement:
        """Ensure the window can contain the work.

        Returns:
            InterventionRequirement: ``self`` for chaining.

        Raises:
            MTRequirementInvalidWindow: If the window does not run forwards, or
                is narrower than the duration.

        Notes:
            An impossible requirement is rejected here rather than handed to
            the solver, which would report it as simply "unassigned" — true,
            but useless for working out why.
        """
        if self.window_end_minute <= self.window_start_minute:
            raise MTRequirementInvalidWindow(
                f"Invalid window: {self.window_start_minute}-"
                f"{self.window_end_minute}. Must run forwards."
            )
        width = self.window_end_minute - self.window_start_minute
        if width < self.duration_minutes:
            raise MTRequirementInvalidWindow(
                f"The window is {width} minutes, which cannot contain a "
                f"{self.duration_minutes}-minute service."
            )
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def latest_start_minute(self) -> int:
        """Return the last minute the work can begin and still finish in time.

        Returns:
            int: The latest permissible start, in minutes from midnight.

        Notes:
            This is the upper bound of the solver's start variable. Computing
            it here keeps the arithmetic in one place rather than repeated at
            every constraint that needs it.
        """
        return self.window_end_minute - self.duration_minutes

    def window_start_time(self) -> time:
        """Return the window's opening as a wall-clock time.

        Returns:
            time: The earliest start.
        """
        return time(
            hour=self.window_start_minute // 60,
            minute=self.window_start_minute % 60,
        )

    def window_end_time(self) -> time:
        """Return the window's closing as a wall-clock time.

        Returns:
            time: The latest finish.
        """
        return time(
            hour=self.window_end_minute // 60,
            minute=self.window_end_minute % 60,
        )

    def requires_certifications(self) -> bool:
        """Return whether any qualification is needed to take this work.

        Returns:
            bool: ``True`` when at least one code is required.

        Notes:
            The solver skips the whole certification constraint for a
            requirement that answers ``False``, which is the common case: most
            work needs nothing, and adding a satisfied-by-everybody constraint
            for every one of them would grow the model for no gain.
        """
        return bool(self.required_certification_codes)

    def requires_skills(self) -> bool:
        """Return whether any declared skill is needed to take this work.

        Returns:
            bool: ``True`` when at least one code is required.

        Notes:
            The solver skips the whole skill constraint for a requirement that
            answers ``False``, which is the common case — the same economy as
            :meth:`requires_certifications`, and worth stating twice because
            most work needs neither and would otherwise carry two
            satisfied-by-everybody constraints per assistant.
        """
        return bool(self.required_skill_codes)
