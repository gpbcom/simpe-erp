from __future__ import annotations

# Standard library imports
from typing import ClassVar, Type

# First-party imports
from models.base.exceptions.organisation_member_exceptions import (
    MTInvalidOrganisationMemberException,
)
from models.base.organisation_member import OrganisationMember
from models.organisation.team.exceptions import (
    MTTeamMemberInvalidId,
    MTTeamMemberInvalidKind,
)


class TeamMember(OrganisationMember):
    """One person on one team.

    Attributes:
        INVALID_KIND (ClassVar[Type[MTInvalidOrganisationMemberException]]):
            Raised for a malformed member kind.
        INVALID_MEMBER_ID (ClassVar[Type[MTInvalidOrganisationMemberException]]):
            Raised for a malformed member identifier.

    Notes:
        - **There is no `is_manager` flag here**, and its absence is the design.
          "Exactly one manager" is a cardinality, and a boolean on a list can
          express zero or five; the manager is a required column on
          :class:`~models.organisation.team.team.Team` instead, which *is* the
          constraint. The manager still gets a membership row, so "a team is a
          list of persons" holds literally.
        - **A person is on at most one team**, enforced by a unique index on the
          row. That is load-bearing rather than tidy: plannings are computed per
          team and stored with a per-team delete, so somebody on two teams would
          have two complete calendars written for the same week by two runs,
          neither of which clears the other's visits. They would be
          double-booked with nothing anywhere reporting it.
    """

    INVALID_KIND: ClassVar[Type[MTInvalidOrganisationMemberException]] = (
        MTTeamMemberInvalidKind
    )
    INVALID_MEMBER_ID: ClassVar[Type[MTInvalidOrganisationMemberException]] = (
        MTTeamMemberInvalidId
    )
