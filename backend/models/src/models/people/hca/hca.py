from __future__ import annotations

# Standard library imports
from datetime import date
from typing import ClassVar, Dict, List, Optional, Tuple, Type, Union

# Third-party imports
from pydantic import (
    Field,
    JsonValue,
    field_validator,
)

# First-party imports
from models.enums import ContractType, Weekday
from models.people.hca.availability_slot import AvailabilitySlot
from models.people.hca.certification import Certification
from models.people.hca.driving_license import DrivingLicense
from models.people.hca.skill import Skill
from models.people.hca.exceptions import (
    MTHcaInvalidAddress,
    MTHcaInvalidAvailability,
    MTHcaInvalidCertifications,
    MTHcaInvalidContractType,
    MTHcaInvalidDate,
    MTHcaInvalidDrivingLicense,
    MTHcaInvalidEmail,
    MTHcaInvalidFieldEmployee,
    MTHcaInvalidFirstName,
    MTHcaInvalidId,
    MTHcaInvalidLastName,
    MTHcaInvalidPhoneNumber,
    MTHcaInvalidPhotoUrl,
    MTHcaInvalidSkills,
    MTHcaInvalidWorkingWeekdays,
)
from models.base.exceptions import MTInvalidPersonException
from models.base.person import Person
from models.base.portrait_holder import PortraitHolder


class Hca(Person, PortraitHolder):
    """A Home Care Assistant: the person who travels to customers.

    Attributes:
        id (Optional[str]): Identifier, populated on read from the store.
            Inherited from :class:`~models.people.person.Person`.
        first_name (str): Given name. Inherited.
        last_name (str): Family name. Inherited.
        phone_number (PhoneNumber): Contact telephone number. Inherited.
        email (EmailStr): Contact email address. Inherited.
        address (PostalAddress): Home address, the start and end of each
            working day's route. Inherited, and load-bearing here in a way it
            is not for a customer — see the note below.
        company_id (str): The company this assistant works for. Required.
        contract_type (ContractType): Employment contract. Editable by a
            manager.
        certifications (List[Certification]): Qualifications held. Editable by
            a manager.
        skills (List[Skill]): Skills declared. Added by the assistant
            themselves, and removed by them, a manager or an administrator.
        driving_license (Optional[DrivingLicense]): Driving licence, when held.
        photo_url (Optional[HttpUrl]): URL of the portrait in the object
            store, when one has been uploaded. Inherited from
            :class:`~models.base.portrait_holder.PortraitHolder`.
        availability (List[AvailabilitySlot]): Periods the assistant cannot
            work. Declared by the assistant themselves.
        working_weekdays (List[Weekday]): The days of the week the assistant
            works at all. Declared by the assistant themselves, and visible to
            their manager.
        field_employee (bool): Whether this person may be placed on an
            intervention planning. Editable by a manager.
        created_at (Optional[datetime]): Creation timestamp, set by the store.
            Inherited.
        updated_at (Optional[datetime]): Last-update timestamp, set by the
            store. Inherited.

    Notes:
       - **The identity half comes from :class:`~models.people.person.Person`**
         — the eight fields above marked *inherited*, their validators, the
         timestamp serializer and :meth:`~models.people.person.Person.full_name`.
         What is declared here is what makes an assistant an *assistant*: who
         employs them, what they are contracted and qualified to do, when they
         work, and whether they go out at all. The ``INVALID_*`` class
         attributes below are how the inherited rules go on raising this
         model's own exceptions.
       - **The portrait comes from
         :class:`~models.base.portrait_holder.PortraitHolder`**, which an
         account inherits too. It is a mixin rather than part of ``Person``
         because a customer and a job applicant have no photograph, and folding
         it into the base would publish an empty field on both.
       - The home address is a routing depot, not just contact information: the
         planner charges the travel from home to the first intervention and back
         from the last, so an assistant living far from their customers is
         assigned differently from one living among them.
       - ``contract_type``, ``certifications`` and ``field_employee`` are the
         only three fields a manager may change. That restriction is enforced
         by the shape of the employment-update request model rather than by a
         check here — there is no manager-reachable route that accepts a whole
         assistant payload, and no assistant-reachable route that accepts any
         of these three.
       - **``skills`` sits on the other side of that line, and is the only
         planner-visible field its owner may write.** A certification is a
         claim about what somebody was awarded, so a manager records it; a
         skill is a claim about what they can do, so they declare it. Letting
         an assistant grant themselves a diploma would put them on work they
         are not trained for; making them ask a manager to record that they
         can operate a hoist is how the agency ends up not knowing. The
         supervisors are told about every addition instead of approving it in
         advance — see :attr:`~models.enums.NotificationKind.SKILL_ADDED` —
         which keeps the declaration instant and still leaves somebody able to
         challenge it before the next run acts on it.
       - ``field_employee`` **defaults to True**, and the default is the whole
         reason the field could be added safely. Every assistant record that
         existed before it did was, by definition, somebody the planner was
         already free to schedule; defaulting to False would have emptied the
         workforce on the deployment that introduced it and failed every
         planning run until somebody ticked a box they had not been told about.
         It is a boolean on the *person*, not a role check, because who goes
         out is not what an account may do: a manager who covers rounds and an
         assistant on office duties are both ordinary, and neither is
         expressible as a :class:`~models.enums.UserRole`.
    """

    INVALID_ID: ClassVar[Type[MTInvalidPersonException]] = MTHcaInvalidId
    INVALID_FIRST_NAME: ClassVar[Type[MTInvalidPersonException]] = MTHcaInvalidFirstName
    INVALID_LAST_NAME: ClassVar[Type[MTInvalidPersonException]] = MTHcaInvalidLastName
    INVALID_PHONE_NUMBER: ClassVar[Type[MTInvalidPersonException]] = (
        MTHcaInvalidPhoneNumber
    )
    INVALID_EMAIL: ClassVar[Type[MTInvalidPersonException]] = MTHcaInvalidEmail
    INVALID_ADDRESS: ClassVar[Type[MTInvalidPersonException]] = MTHcaInvalidAddress
    INVALID_DATE: ClassVar[Type[MTInvalidPersonException]] = MTHcaInvalidDate
    INVALID_PHOTO_URL: ClassVar[Type[MTInvalidPersonException]] = MTHcaInvalidPhotoUrl

    DEFAULT_WORKING_WEEKDAYS: ClassVar[Tuple[Weekday, ...]] = (
        Weekday.MONDAY,
        Weekday.TUESDAY,
        Weekday.WEDNESDAY,
        Weekday.THURSDAY,
        Weekday.FRIDAY,
    )

    company_id: str = Field(description="The company this assistant works for.")
    contract_type: ContractType = Field(description="Employment contract.")
    certifications: List[Certification] = Field(
        default_factory=list,
        description="Qualifications held.",
    )
    skills: List[Skill] = Field(
        default_factory=list,
        description="Skills declared by the assistant themselves.",
    )
    driving_license: Optional[DrivingLicense] = Field(
        default=None,
        description="Driving licence, when held.",
    )
    availability: List[AvailabilitySlot] = Field(
        default_factory=list,
        description="Periods the assistant cannot work.",
    )
    working_weekdays: List[Weekday] = Field(
        default_factory=lambda: list(Hca.DEFAULT_WORKING_WEEKDAYS),
        description="The days of the week the assistant works at all.",
    )
    field_employee: bool = Field(
        default=True,
        description="Whether this person may be placed on an intervention planning.",
    )

    @field_validator("contract_type", mode="before")
    def validate_contract_type(
        cls, value: Union[str, ContractType, None]
    ) -> ContractType:
        """Validates that ``contract_type`` is a known contract type.

        Args:
            value (Union[str, ContractType, None]): Raw ``contract_type`` value.

        Returns:
            ContractType: The coerced contract type.

        Raises:
            MTHcaInvalidContractType: If ``value`` is not a known contract type.
        """
        if isinstance(value, ContractType):
            return value
        try:
            return ContractType(value)
        except ValueError:
            raise MTHcaInvalidContractType(
                f"Invalid contract_type: {value!r}. Must be one of: "
                f"{', '.join(ContractType.values())}."
            ) from None

    @field_validator("certifications", mode="before")
    def validate_certifications(cls, value: JsonValue) -> JsonValue:
        """Validates that ``certifications`` is a list of qualifications.

        Args:
            value (JsonValue): Raw list of certification payloads. ``None``
                yields an empty list.

        Returns:
            JsonValue: The list handed back for Pydantic to build.

        Raises:
            MTHcaInvalidCertifications: If ``value`` is neither ``None`` nor a
                list, or if an entry is neither a mapping nor a built
                certification.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTHcaInvalidCertifications(
                f"Invalid certifications: {value!r}. Must be a list or None."
            )
        for entry in value:
            if not isinstance(entry, (Certification, dict)):
                raise MTHcaInvalidCertifications(
                    f"Invalid certifications entry: {entry!r}. "
                    f"Must be a Certification or a mapping."
                )
        return value

    @field_validator("skills", mode="before")
    def validate_skills(cls, value: JsonValue) -> JsonValue:
        """Validates that ``skills`` is a list of declared skills.

        Args:
            value (JsonValue): Raw list of skill payloads. ``None`` yields an
                empty list.

        Returns:
            JsonValue: The list handed back for Pydantic to build.

        Raises:
            MTHcaInvalidSkills: If ``value`` is neither ``None`` nor a list, or
                if an entry is neither a mapping nor a built skill.

        Notes:
            ``None`` becomes an empty list rather than being refused, which is
            what lets a row written before the ``skills`` table existed read
            back as somebody who has simply declared nothing yet — the honest
            reading, and the one that leaves them assignable to every piece of
            work that requires no skill.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTHcaInvalidSkills(
                f"Invalid skills: {value!r}. Must be a list or None."
            )
        for entry in value:
            if not isinstance(entry, (Skill, dict)):
                raise MTHcaInvalidSkills(
                    f"Invalid skills entry: {entry!r}. Must be a Skill or a mapping."
                )
        return value

    @field_validator("driving_license", mode="before")
    def validate_driving_license(
        cls, value: Union[DrivingLicense, Dict[str, JsonValue], None]
    ) -> Union[DrivingLicense, Dict[str, JsonValue], None]:
        """Validates that ``driving_license`` is a licence, a mapping or ``None``.

        Args:
            value (Union[DrivingLicense, Dict[str, JsonValue], None]): Raw
                ``driving_license`` value.

        Returns:
            Union[DrivingLicense, Dict[str, JsonValue], None]: The value handed
            back for Pydantic to build.

        Raises:
            MTHcaInvalidDrivingLicense: If ``value`` is neither ``None``, a
                :class:`~models.people.hca.driving_license.DrivingLicense`, nor a
                mapping.
        """
        if value is None:
            return None
        if not isinstance(value, (DrivingLicense, dict)):
            raise MTHcaInvalidDrivingLicense(
                f"Invalid driving_license: {value!r}. "
                f"Must be a DrivingLicense, a mapping, or None."
            )
        return value

    @field_validator("company_id", mode="before")
    def validate_company_id(cls, value: Optional[str]) -> str:
        """Validates that ``company_id`` names the agency this assistant works for.

        Args:
            value (Optional[str]): Raw ``company_id`` value.

        Returns:
            str: The identifier.

        Raises:
            MTHcaInvalidId: If ``value`` is not a non-empty string.

        Notes:
            **Required.** It was optional while assistants predated companies,
            and every one of them has been given an agency since. An assistant
            without one cannot be planned against an agency's settings, cannot
            be scoped by any per-company query, and produces events that cannot
            be routed to an agency's queue — so the field no longer allows the
            state that made those possible.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTHcaInvalidId(
                f"Invalid company_id: {value!r}. Must be a non-empty string "
                f"naming the agency this assistant works for."
            )
        return value.strip()

    @field_validator("availability", mode="before")
    def validate_availability(cls, value: JsonValue) -> JsonValue:
        """Validates that ``availability`` is a list of unavailability slots.

        Args:
            value (JsonValue): Raw list of slot payloads. ``None`` yields an
                empty list.

        Returns:
            JsonValue: The list handed back for Pydantic to build.

        Raises:
            MTHcaInvalidAvailability: If ``value`` is neither ``None`` nor a
                list, or if an entry is neither a mapping nor a built slot.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTHcaInvalidAvailability(
                f"Invalid availability: {value!r}. Must be a list or None."
            )
        for entry in value:
            if not isinstance(entry, (AvailabilitySlot, dict)):
                raise MTHcaInvalidAvailability(
                    f"Invalid availability entry: {entry!r}. "
                    f"Must be an AvailabilitySlot or a mapping."
                )
        return value

    @field_validator("working_weekdays", mode="before")
    def validate_working_weekdays(cls, value: JsonValue) -> List[Weekday]:
        """Validates that ``working_weekdays`` names known days of the week.

        Args:
            value (JsonValue): Raw list of weekday values. ``None`` yields the
                default working week.

        Returns:
            List[Weekday]: The days worked, deduplicated and ordered Monday
            first.

        Raises:
            MTHcaInvalidWorkingWeekdays: If ``value`` is neither ``None`` nor a
                list, if it is empty, or if an entry is not a known weekday.

        Notes:
            - **The result is sorted and deduplicated here rather than left as
              the caller sent it.** The set is compared and stored as a string,
              so ``["friday", "monday"]`` and ``["monday", "friday"]`` must not
              produce two different rows for the same working week.
            - An empty list is refused rather than read as the default. Somebody
              clearing every checkbox means "I work no days", which is not a
              working pattern — and silently restoring Monday-to-Friday would
              put them back on rounds they had just declined.
        """
        if value is None:
            return list(cls.DEFAULT_WORKING_WEEKDAYS)
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise MTHcaInvalidWorkingWeekdays(
                f"Invalid working_weekdays: {value!r}. Must be a list or None."
            )
        days: List[Weekday] = []
        for entry in value:
            if isinstance(entry, Weekday):
                days.append(entry)
                continue
            try:
                days.append(Weekday(entry))
            except ValueError:
                raise MTHcaInvalidWorkingWeekdays(
                    f"Invalid working_weekdays entry: {entry!r}. Must be one "
                    f"of: {', '.join(Weekday.values())}."
                ) from None
        if not days:
            raise MTHcaInvalidWorkingWeekdays(
                "Invalid working_weekdays: at least one day must be worked."
            )
        return sorted(set(days), key=lambda day: day.iso_weekday())

    @field_validator("field_employee", mode="before")
    def validate_field_employee(cls, value: Union[bool, str, int, None]) -> bool:  # noqa: E501
        """Validates that ``field_employee`` is a boolean.

        Args:
            value (Union[bool, str, int, None]): Raw ``field_employee`` value.
                ``None`` falls back to ``True``.

        Returns:
            bool: The validated flag.

        Raises:
            MTHcaInvalidFieldEmployee: If ``value`` is neither ``None`` nor a
                boolean.

        Notes:
            - Strings are refused rather than coerced, for the same reason
              :meth:`~models.auth.user.User.validate_must_change_password`
              refuses them: ``"false"`` is truthy, and a stored ``"false"`` read
              as "may be scheduled" would put somebody who does not go out onto a
              round — while the reverse would quietly withdraw an assistant from
              the workforce with nothing on any screen to say why.
            - ``None`` falls back to ``True`` so a row written before the column
              existed reads back as schedulable, which is what it was.
        """
        if value is None:
            return True
        if not isinstance(value, bool):
            raise MTHcaInvalidFieldEmployee(
                f"Invalid field_employee: {value!r}. Must be true or false."
            )
        return value

    def can_drive(self) -> bool:
        """Return whether the assistant may be routed at driving speed.

        Returns:
            bool: ``True`` when a licence is held that permits driving a car.

        Notes:
            Used by the planner to pick which travel-time matrix applies. An
            assistant with no licence, or with a motorcycle-only licence, is
            routed at the slower transit speed.
        """
        if self.driving_license is None:
            return False
        return self.driving_license.can_drive_a_car()

    def works_on_weekday(self, day: date) -> bool:
        """Return whether the assistant works that day of the week at all.

        Args:
            day (date): The day to test.

        Returns:
            bool: ``True`` when the day falls on one of
            :attr:`working_weekdays`.

        Notes:
            This is the *recurring* pattern — "never Wednesdays" — and it is
            deliberately separate from :meth:`is_available_on`, which answers
            the *dated* question "are they away that week?". Folding the two
            together would be cheaper by one method call and would cost the
            unplaced-work report its ability to tell a manager which of the
            two to change: hiring cover for a Wednesday and waiting for
            somebody to come back from leave are different actions.
        """
        return Weekday.from_iso_weekday(day.isoweekday()) in self.working_weekdays  # noqa: E501

    def is_available_on(self, day: date) -> bool:
        """Return whether the assistant can take work on a given day.

        Args:
            day (date): The day to test.

        Returns:
            bool: ``False`` when a whole-day unavailability slot covers the
            day, ``True`` otherwise.

        Notes:
            - A partial-day slot leaves the day workable — it only carves a
              window out of it, which the solver models as a blocking interval
              rather than as an absence.
            - This answers only the *dated* question. A day the assistant never
              works is not an absence; see :meth:`works_on_weekday`.
        """
        return not any(
            slot.covers(day) and slot.is_whole_day()
            for slot in self.availability  # noqa: E501
        )

    def is_schedulable_on(self, day: date) -> bool:
        """Return whether the assistant may be given work on a given day.

        Args:
            day (date): The day to test.

        Returns:
            bool: ``True`` only when the day is one they work and no whole-day
            absence covers it.

        Notes:
            The conjunction the solver actually needs. Both halves have to
            hold, and having one method say so keeps the two call sites — the
            constraint and the diagnosis — from drifting apart.
        """
        return self.works_on_weekday(day) and self.is_available_on(day)

    def blocking_slots_on(self, day: date) -> List[AvailabilitySlot]:
        """Return the partial-day slots that block part of a given day.

        Args:
            day (date): The day to inspect.

        Returns:
            List[AvailabilitySlot]: The slots covering ``day`` that block only
            a window of it.

        Notes:
            The solver turns each of these into a fixed interval that no
            intervention may overlap.
        """
        return [
            slot
            for slot in self.availability
            if slot.covers(day) and not slot.is_whole_day()
        ]

    def holds_certifications(self, codes: List[str], day: date) -> bool:
        """Return whether the assistant is qualified for a piece of work.

        Args:
            codes (List[str]): Every certification code the work requires.
            day (date): The day the work happens, against which each
                qualification's expiry is tested.

        Returns:
            bool: ``True`` when the assistant holds an unlapsed qualification
            for **every** code. Work requiring nothing is satisfied by
            everybody.

        Notes:
            - **Every code, not any.** A requirement listing two diplomas means
              the person needs both; reading it as "one of these" would send
              somebody to a visit half-qualified, which is the failure this
              whole field exists to prevent.
            - The expiry is tested against the day of the visit rather than
              today, so a plan built a fortnight out does not hand work to
              somebody whose certificate lapses before they get there. See
              :meth:`~models.people.hca.certification.Certification.satisfies`.
        """
        return all(
            any(held.satisfies(code, day) for held in self.certifications)
            for code in codes
        )

    def holds_skills(self, codes: List[str], day: date) -> bool:
        """Return whether the assistant declares every skill a piece of work needs.

        Args:
            codes (List[str]): Every skill code the work requires.
            day (date): The day the work happens, against which each declared
                skill's expiry is tested.

        Returns:
            bool: ``True`` when the assistant declares an unlapsed skill for
            **every** code. Work requiring nothing is satisfied by everybody.

        Notes:
            - **Every code, not any**, and the expiry judged on the day of the
              visit — the same two rules as :meth:`holds_certifications`, for
              the same two reasons.
            - Deliberately a second method rather than one that takes both
              kinds of code. The two are satisfied from different lists and the
              planner reports them as different unplaced reasons, so a caller
              that could only ask "is this person eligible?" would lose the one
              piece of information the answer is worth having for: which of the
              two a manager has to go and fix.
        """
        return all(
            any(declared.satisfies(code, day) for declared in self.skills)
            for code in codes
        )
