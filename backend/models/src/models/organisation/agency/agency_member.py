from __future__ import annotations

# Standard library imports
from typing import ClassVar, Type

# First-party imports
from models.base.exceptions.organisation_member_exceptions import (
    MTInvalidOrganisationMemberException,
)
from models.base.organisation_member import OrganisationMember
from models.organisation.agency.exceptions import (
    MTAgencyMemberInvalidId,
    MTAgencyMemberInvalidKind,
)


class AgencyMember(OrganisationMember):
    """One person attached to one of a company's sites.

    Attributes:
        INVALID_KIND (ClassVar[Type[MTInvalidOrganisationMemberException]]):
            Raised for a malformed member kind.
        INVALID_MEMBER_ID (ClassVar[Type[MTInvalidOrganisationMemberException]]):
            Raised for a malformed member identifier.

    Notes:
        - It adds no field to its base, and that is the point: a person's place
          in a site is the pair *(what kind of record, which record)* and
          nothing else. A role would be a second copy of ``User.role``, free to
          disagree with it.
        - **Everybody belongs to exactly one site**, which is enforced by a
          unique index on the membership row rather than by anything here — a
          value cannot answer a question about other rows.
    """

    INVALID_KIND: ClassVar[Type[MTInvalidOrganisationMemberException]] = (
        MTAgencyMemberInvalidKind
    )
    INVALID_MEMBER_ID: ClassVar[Type[MTInvalidOrganisationMemberException]] = (
        MTAgencyMemberInvalidId
    )
