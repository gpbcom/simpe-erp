from __future__ import annotations

# Standard library imports
from datetime import datetime, timezone

# Third-party imports
import pytest

# First-party imports
from models.organisation.team import Team
from models.organisation.team.exceptions import (
    MTTeamInvalidAgencyId,
    MTTeamInvalidCompanyId,
    MTTeamInvalidDate,
    MTTeamInvalidId,
    MTTeamInvalidManagerUserId,
    MTTeamInvalidName,
)
from tests.annotations import ModelInput


def _team(**overrides: ModelInput) -> Team:
    """Return a valid team, with any field replaced.

    Args:
        **overrides (ModelInput): Fields to replace on the fixture.

    Returns:
        Team: The team, built from the overridden values.
    """
    fields = {
        "company_id": "company-1",
        "agency_id": "agency-1",
        "name": "Equipe Est",
        "manager_user_id": "user-1",
    }
    fields.update(overrides)
    return Team(**fields)


class TestTeam:
    """Tests for the Team model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_minimal_valid_construction(self) -> None:
        """A team is a company, a site, a name and one manager."""
        team = _team()
        assert team.company_id == "company-1"
        assert team.agency_id == "agency-1"
        assert team.name == "Equipe Est"
        assert team.manager_user_id == "user-1"
        assert team.id is None

    def test_whitespace_is_trimmed_everywhere(self) -> None:
        """No stored identifier carries surrounding whitespace."""
        team = _team(
            id="  t-1 ",
            company_id=" c-1 ",
            agency_id=" a-1 ",
            name="  Equipe  ",
            manager_user_id=" u-1 ",
        )
        assert (team.id, team.company_id, team.agency_id) == ("t-1", "c-1", "a-1")
        assert (team.name, team.manager_user_id) == ("Equipe", "u-1")

    def test_there_is_no_is_manager_flag_on_the_team(self) -> None:
        """The manager is a required field, never a flag on a list.

        Notes:
            "Exactly one" is a cardinality, and a boolean on the membership
            rows can express zero or five. A required column is the constraint.
        """
        assert Team.model_fields["manager_user_id"].is_required()

    # ------------------------------------------------------------------ #
    #  id validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_id",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("  ", id="Invalid - whitespace only"),
            pytest.param(5, id="Invalid - not a string"),
        ],
    )
    def test_a_malformed_id_is_refused(self, invalid_id: ModelInput) -> None:
        """A present identifier must be a non-empty string."""
        with pytest.raises(MTTeamInvalidId):
            _team(id=invalid_id)

    def test_a_missing_id_is_accepted(self) -> None:
        """The identifier is absent until the store assigns one."""
        assert _team().id is None

    # ------------------------------------------------------------------ #
    #  company_id, agency_id and manager_user_id validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            pytest.param("company_id", MTTeamInvalidCompanyId, id="company"),
            pytest.param("agency_id", MTTeamInvalidAgencyId, id="agency"),
            pytest.param("manager_user_id", MTTeamInvalidManagerUserId, id="manager"),
        ],
    )
    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - whitespace only"),
            pytest.param(6, id="Invalid - not a string"),
        ],
    )
    def test_the_three_required_links_each_raise_their_own_exception(
        self, field: str, expected: type, invalid_value: ModelInput
    ) -> None:
        """Each link is refused with a message naming which one it was.

        Notes:
            Three exceptions rather than one, because the API's map is keyed on
            the class and "this team names no site" and "this team names no
            manager" send a reader to two different forms.
        """
        with pytest.raises(expected):
            _team(**{field: invalid_value})

    # ------------------------------------------------------------------ #
    #  name validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_name",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - whitespace only"),
            pytest.param(2, id="Invalid - not a string"),
        ],
    )
    def test_a_malformed_name_is_refused(self, invalid_name: ModelInput) -> None:
        """A team nobody can name is a team nobody can pick."""
        with pytest.raises(MTTeamInvalidName):
            _team(name=invalid_name)

    def test_a_name_at_the_limit_is_accepted(self) -> None:
        """The length bound is inclusive."""
        name = "e" * Team.MAX_NAME_LENGTH
        assert _team(name=name).name == name

    def test_a_name_past_the_limit_is_refused(self) -> None:
        """One character over the bound is refused."""
        with pytest.raises(MTTeamInvalidName):
            _team(name="e" * (Team.MAX_NAME_LENGTH + 1))

    # ------------------------------------------------------------------ #
    #  timestamp validation
    # ------------------------------------------------------------------ #

    def test_timestamps_are_parsed_from_iso_strings(self) -> None:
        """A store hands them back as text."""
        team = _team(created_at="2026-08-12T09:00:00+00:00")
        assert team.created_at == datetime(2026, 8, 12, 9, tzinfo=timezone.utc)

    @pytest.mark.parametrize(
        "invalid_timestamp",
        [
            pytest.param("yesterday", id="Invalid - unparseable"),
            pytest.param(11, id="Invalid - a number"),
        ],
    )
    def test_a_malformed_timestamp_is_refused(
        self, invalid_timestamp: ModelInput
    ) -> None:
        """Anything that is not a datetime is refused."""
        with pytest.raises(MTTeamInvalidDate):
            _team(updated_at=invalid_timestamp)

    def test_timestamps_serialise_as_iso_strings(self) -> None:
        """The wire form is ISO-8601."""
        team = _team(updated_at=datetime(2026, 8, 12, 11, tzinfo=timezone.utc))
        assert team.model_dump()["updated_at"] == "2026-08-12T11:00:00+00:00"

    # ------------------------------------------------------------------ #
    #  Behaviour
    # ------------------------------------------------------------------ #

    def test_the_manager_runs_the_team(self) -> None:
        """The narrowing every manager screen rests on."""
        assert _team().is_managed_by("user-1")
        assert not _team().is_managed_by("user-2")

    def test_an_account_with_no_identifier_runs_nothing(self) -> None:
        """``None`` answers ``False`` rather than matching.

        Notes:
            The caller's identifier is typed optional, so a check that read a
            missing one as a match would hand a manager every team the moment
            one account arrived without one.
        """
        assert not _team().is_managed_by(None)
