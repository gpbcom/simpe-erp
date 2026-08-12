from __future__ import annotations

# Standard library imports
from typing import ClassVar, Type, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.base.exceptions.organisation_member_exceptions import (
    MTInvalidOrganisationMemberException,
    MTOrganisationMemberInvalidId,
    MTOrganisationMemberInvalidKind,
)
from models.enums import MemberKind


class OrganisationMember(BaseModel):
    """One person's place in an agency or a team, and nothing more.

    Attributes:
        INVALID_KIND (ClassVar[Type[MTInvalidOrganisationMemberException]]):
            Exception a subclass raises for a malformed member kind.
        INVALID_MEMBER_ID (ClassVar[Type[MTInvalidOrganisationMemberException]]):
            Same, for a malformed member identifier.
        member_kind (MemberKind): Whether ``member_id`` names a sign-in account
            or an assistant record.
        member_id (str): The identifier of that account or record.

    Notes:
        - **A base, not an entity.** Nothing stores an ``OrganisationMember``;
          :class:`~models.organisation.agency.AgencyMember` and
          :class:`~models.organisation.team.TeamMember` do. They existed as two
          identical copies of the same two rules for about an hour, which is
          exactly the shape :class:`~models.base.person.Person` was extracted
          from.
        - The per-model exceptions survive the move: each subclass declares
          ``INVALID_KIND`` and ``INVALID_MEMBER_ID`` as class attributes, the
          shared validator raises ``cls.INVALID_*``, and Pydantic binds ``cls``
          to the concrete subclass. That is not tidiness — ``api``'s
          exception-to-status map is keyed on those classes, so one shared
          exception would answer a bad agency membership and a bad team
          membership with the same status and the same words.
        - There is deliberately **no `agency_id` or `team_id` here**. The owning
          aggregate comes from the route and is applied by the repository, so a
          payload cannot file a person into a team it was not sent to — the
          absence *is* the control, the same way
          :class:`~models.schemas.requests.hca.skill_create_request.SkillCreateRequest`
          carries no ``hca_id``.
    """

    INVALID_KIND: ClassVar[Type[MTInvalidOrganisationMemberException]] = (
        MTOrganisationMemberInvalidKind
    )
    INVALID_MEMBER_ID: ClassVar[Type[MTInvalidOrganisationMemberException]] = (
        MTOrganisationMemberInvalidId
    )

    member_kind: MemberKind = Field(
        description="Whether the member is an account or an assistant record."
    )
    member_id: str = Field(description="Identifier of that account or record.")

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("member_kind", mode="before")
    def validate_member_kind(cls, value: Union[MemberKind, str, None]) -> MemberKind:
        """Validates that ``member_kind`` names a known kind of person.

        Args:
            value (Union[MemberKind, str, None]): Raw ``member_kind`` value.

        Returns:
            MemberKind: The member kind.

        Raises:
            MTInvalidOrganisationMemberException: The subclass's
                ``INVALID_KIND``, if ``value`` is not one of the two kinds.

        Notes:
            There is no default. Guessing ``hca`` would file every manager as an
            assistant record that does not exist, and guessing ``user`` would
            silently exclude every assistant who has no sign-in account from
            every planning run — two opposite failures, neither visible on any
            screen.
        """
        if isinstance(value, MemberKind):
            return value
        if isinstance(value, str):
            try:
                return MemberKind(value)
            except ValueError:
                raise cls.INVALID_KIND(
                    f"Invalid member_kind: {value!r}. Must be one of "
                    f"{MemberKind.values()}."
                ) from None
        raise cls.INVALID_KIND(
            f"Invalid member_kind: {value!r}. Must be one of {MemberKind.values()}."
        )

    @field_validator("member_id", mode="before")
    def validate_member_id(cls, value: Union[str, None]) -> str:
        """Validates that ``member_id`` is a usable identifier.

        Args:
            value (Union[str, None]): Raw ``member_id`` value.

        Returns:
            str: The trimmed identifier.

        Raises:
            MTInvalidOrganisationMemberException: The subclass's
                ``INVALID_MEMBER_ID``, if ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise cls.INVALID_MEMBER_ID(
                f"Invalid member_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_assistant(self) -> bool:
        """Return whether this membership names an assistant record.

        Returns:
            bool: ``True`` when the kind is :attr:`MemberKind.HCA`.

        Notes:
            The planner is handed assistant records, so this is the question
            that decides whether a member contributes to a team's workforce at
            all. Written as a method so the two callers that ask it — the
            workforce pool and the member view — cannot spell it differently.
        """
        return self.member_kind is MemberKind.HCA
