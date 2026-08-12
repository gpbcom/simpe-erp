from __future__ import annotations

# Standard library imports
from typing import Type

# Third-party imports
import pytest

# First-party imports
from models.base.exceptions.organisation_member_exceptions import (
    MTInvalidOrganisationMemberException,
    MTOrganisationMemberInvalidId,
    MTOrganisationMemberInvalidKind,
)
from models.base.organisation_member import OrganisationMember
from models.enums import MemberKind
from models.organisation.agency import AgencyMember
from models.organisation.agency.exceptions import (
    MTAgencyMemberInvalidId,
    MTAgencyMemberInvalidKind,
)
from models.organisation.team import TeamMember
from models.organisation.team.exceptions import (
    MTTeamMemberInvalidId,
    MTTeamMemberInvalidKind,
)
from tests.annotations import ModelInput


class TestOrganisationMember:
    """Tests for the shared membership base and its two subclasses."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("model", [AgencyMember, TeamMember, OrganisationMember])
    def test_minimal_valid_construction(self, model: Type[OrganisationMember]) -> None:
        """A membership is a kind and an identifier, and nothing else."""
        member = model(member_kind="hca", member_id="hca-1")
        assert member.member_kind is MemberKind.HCA
        assert member.member_id == "hca-1"

    @pytest.mark.parametrize("model", [AgencyMember, TeamMember])
    def test_the_identifier_is_trimmed(self, model: Type[OrganisationMember]) -> None:
        """Surrounding whitespace never reaches the store."""
        assert model(member_kind="user", member_id="  u-1 ").member_id == "u-1"

    @pytest.mark.parametrize("model", [AgencyMember, TeamMember])
    def test_a_membership_carries_no_owning_identifier(
        self, model: Type[OrganisationMember]
    ) -> None:
        """There is no ``agency_id`` or ``team_id`` a payload could set.

        Notes:
            The absence *is* the control. The owning aggregate comes from the
            route and is applied by the repository, so a payload cannot file a
            person into a team it was not sent to.
        """
        assert "agency_id" not in model.model_fields
        assert "team_id" not in model.model_fields

    # ------------------------------------------------------------------ #
    #  member_kind validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("kind", list(MemberKind))
    def test_every_declared_kind_is_accepted(self, kind: MemberKind) -> None:
        """Both halves of the person model are expressible."""
        assert AgencyMember(member_kind=kind, member_id="x").member_kind is kind

    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            pytest.param(AgencyMember, MTAgencyMemberInvalidKind, id="agency"),
            pytest.param(TeamMember, MTTeamMemberInvalidKind, id="team"),
            pytest.param(
                OrganisationMember, MTOrganisationMemberInvalidKind, id="base default"
            ),
        ],
    )
    @pytest.mark.parametrize(
        "invalid_kind",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param("customer", id="Invalid - not a member"),
            pytest.param(4, id="Invalid - not a string"),
        ],
    )
    def test_each_model_raises_its_own_exception_for_the_kind(
        self,
        model: Type[OrganisationMember],
        expected: Type[MTInvalidOrganisationMemberException],
        invalid_kind: ModelInput,
    ) -> None:
        """Pydantic binds ``cls`` to the concrete subclass.

        Notes:
            This is what the API's exception-to-status map is keyed on. One
            shared exception would answer a bad agency membership and a bad team
            membership with the same status and the same words.
        """
        with pytest.raises(expected):
            model(member_kind=invalid_kind, member_id="x")

    def test_a_kind_is_never_guessed(self) -> None:
        """There is no default, and that is deliberate.

        Notes:
            Guessing ``hca`` would file every manager as an assistant record
            that does not exist; guessing ``user`` would drop every assistant
            without a sign-in account out of the workforce. Two opposite
            failures, neither of them visible on a screen.
        """
        assert AgencyMember.model_fields["member_kind"].is_required()

    # ------------------------------------------------------------------ #
    #  member_id validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            pytest.param(AgencyMember, MTAgencyMemberInvalidId, id="agency"),
            pytest.param(TeamMember, MTTeamMemberInvalidId, id="team"),
            pytest.param(
                OrganisationMember, MTOrganisationMemberInvalidId, id="base default"
            ),
        ],
    )
    @pytest.mark.parametrize(
        "invalid_member_id",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - whitespace only"),
            pytest.param(9, id="Invalid - not a string"),
        ],
    )
    def test_each_model_raises_its_own_exception_for_the_identifier(
        self,
        model: Type[OrganisationMember],
        expected: Type[MTInvalidOrganisationMemberException],
        invalid_member_id: ModelInput,
    ) -> None:
        """The identifier half is per-model too."""
        with pytest.raises(expected):
            model(member_kind="user", member_id=invalid_member_id)

    # ------------------------------------------------------------------ #
    #  Behaviour
    # ------------------------------------------------------------------ #

    def test_only_an_assistant_record_is_an_assistant(self) -> None:
        """The workforce pool is built from exactly this question."""
        assert AgencyMember(member_kind="hca", member_id="h").is_assistant()
        assert not AgencyMember(member_kind="user", member_id="u").is_assistant()
