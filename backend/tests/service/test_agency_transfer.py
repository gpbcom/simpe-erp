from __future__ import annotations

# Standard library imports
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.enums import AgencyType, MemberKind, UserRole
from models.organisation.agency.agency import Agency
from models.organisation.agency.agency_member import AgencyMember
from models.organisation.team.team import Team
from service.organisation.agencies import AgencyService
from service.organisation.exceptions import MTAgencyMemberRunsATeam


def _agency(agency_id: str, name: str = "Antenne Est") -> Agency:
    """Build a stored site.

    Args:
        agency_id (str): Its identifier.
        name (str): What it is called.

    Returns:
        Agency: The site.
    """
    return Agency(
        id=agency_id,
        company_id="company-1",
        name=name,
        agency_type=AgencyType.OFFICE,
    )


def _team(team_id: str, agency_id: str, manager: str = "user-9") -> Team:
    """Build a stored team at a site.

    Args:
        team_id (str): Its identifier.
        agency_id (str): The site it works from.
        manager (str): The account that runs it.

    Returns:
        Team: The team.
    """
    return Team(
        id=team_id,
        company_id="company-1",
        agency_id=agency_id,
        name="Équipe Est",
        manager_user_id=manager,
    )


def _caller() -> User:
    """Build the administrator doing the transfer.

    Returns:
        User: The account.
    """
    return User(
        id="user-1",
        email="camille@simple-erp.fr",
        full_name="Camille Fournier",
        hashed_password="x" * 20,
        role=UserRole.ADMIN,
        company_id="company-1",
    )


@pytest.fixture
def agencies() -> AsyncMock:
    """Return a stubbed site store.

    Returns:
        AsyncMock: The store double, holding the destination site.
    """
    stub = AsyncMock()
    stub.get.return_value = _agency("agency-2", "Antenne Ouest")
    stub.agency_for_member.return_value = _agency("agency-1")
    stub.add_member.side_effect = lambda agency_id, member: member
    stub.remove_member.return_value = True
    return stub


@pytest.fixture
def teams() -> AsyncMock:
    """Return a stubbed team store.

    Returns:
        AsyncMock: The store double, with nobody on a team.
    """
    stub = AsyncMock()
    stub.team_for_member.return_value = None
    stub.remove_member.return_value = True
    return stub


@pytest.fixture
def service(agencies: AsyncMock, teams: AsyncMock) -> AgencyService:
    """Return the service under test.

    Args:
        agencies (AsyncMock): The site store.
        teams (AsyncMock): The team store.

    Returns:
        AgencyService: The service.
    """
    return AgencyService(
        agencies=agencies,
        companies=AsyncMock(),
        teams=teams,
        logger=MagicMock(),
    )


class TestMovingSomebodyBetweenSites:
    """Tests for attaching somebody who already works somewhere else."""

    async def test_the_old_membership_goes_and_the_new_one_lands(
        self, service: AgencyService, agencies: AsyncMock
    ) -> None:
        """**A transfer, not a refusal.**

        Notes:
            Somebody moving site does it once, on one screen. Requiring a detach
            first would be two forms for one act, and the state in between — a
            person attached to no site — is one nothing else expects.
        """
        member = AgencyMember(member_kind=MemberKind.HCA, member_id="hca-1")

        stored = await service.add_member("agency-2", member, _caller())

        assert stored.member_id == "hca-1"
        agencies.remove_member.assert_awaited_once_with(MemberKind.HCA, "hca-1")
        assert agencies.add_member.await_args.args[0] == "agency-2"

    async def test_the_old_membership_goes_first(
        self, service: AgencyService, agencies: AsyncMock
    ) -> None:
        """Everybody belongs to exactly one site, and an index says so.

        Notes:
            Inserting before deleting would collide with the unique membership
            index, and the caller would see an opaque database error rather than
            a transfer.
        """
        order: list[str] = []
        agencies.remove_member.side_effect = lambda *_: order.append("removed") or True
        agencies.add_member.side_effect = lambda _agency, member: (
            order.append("added") or member
        )

        await service.add_member(
            "agency-2",
            AgencyMember(member_kind=MemberKind.HCA, member_id="hca-1"),
            _caller(),
        )

        assert order == ["removed", "added"]

    async def test_attaching_somebody_already_here_changes_nothing(
        self, service: AgencyService, agencies: AsyncMock
    ) -> None:
        """A no-op rather than a delete-and-reinsert of the same row."""
        agencies.agency_for_member.return_value = _agency("agency-2")

        await service.add_member(
            "agency-2",
            AgencyMember(member_kind=MemberKind.HCA, member_id="hca-1"),
            _caller(),
        )

        agencies.remove_member.assert_not_awaited()
        agencies.add_member.assert_not_awaited()

    async def test_somebody_on_no_site_is_simply_attached(
        self, service: AgencyService, agencies: AsyncMock
    ) -> None:
        """The ordinary first attachment still works."""
        agencies.agency_for_member.return_value = None

        await service.add_member(
            "agency-2",
            AgencyMember(member_kind=MemberKind.HCA, member_id="hca-1"),
            _caller(),
        )

        agencies.remove_member.assert_not_awaited()
        agencies.add_member.assert_awaited_once()


class TestWhatHappensToTheirTeam:
    """Tests for the consequence a site transfer has on team membership."""

    async def test_they_come_off_a_team_based_at_the_old_site(
        self, service: AgencyService, teams: AsyncMock
    ) -> None:
        """**A team is people at a place.**

        Notes:
            The planner measures every round from the team's site, so somebody
            kept on a team based where they no longer work would be routed from
            a depot they never travel to.
        """
        teams.team_for_member.return_value = _team("team-1", "agency-1")

        await service.add_member(
            "agency-2",
            AgencyMember(member_kind=MemberKind.HCA, member_id="hca-1"),
            _caller(),
        )

        teams.remove_member.assert_awaited_once_with(MemberKind.HCA, "hca-1")

    async def test_a_team_at_the_same_site_is_left_alone(
        self, service: AgencyService, teams: AsyncMock
    ) -> None:
        """Moving between teams at one site is a different act, done elsewhere."""
        teams.team_for_member.return_value = _team("team-1", "agency-2")

        await service.add_member(
            "agency-2",
            AgencyMember(member_kind=MemberKind.HCA, member_id="hca-1"),
            _caller(),
        )

        teams.remove_member.assert_not_awaited()

    async def test_a_manager_of_that_team_is_refused(
        self, service: AgencyService, teams: AsyncMock, agencies: AsyncMock
    ) -> None:
        """The one case left that a transfer cannot decide on its own.

        Notes:
            A team's manager is a required column, so there is no state in which
            a team briefly has none — and choosing a replacement is not
            something a site transfer should do silently.
        """
        teams.team_for_member.return_value = _team("team-1", "agency-1", "user-7")

        with pytest.raises(MTAgencyMemberRunsATeam):
            await service.add_member(
                "agency-2",
                AgencyMember(member_kind=MemberKind.USER, member_id="user-7"),
                _caller(),
            )

        agencies.remove_member.assert_not_awaited()
        agencies.add_member.assert_not_awaited()

    async def test_the_refusal_happens_before_anything_is_written(
        self, service: AgencyService, teams: AsyncMock, agencies: AsyncMock
    ) -> None:
        """A half-applied transfer would leave the team's manager at no site."""
        teams.team_for_member.return_value = _team("team-1", "agency-1", "user-7")

        with pytest.raises(MTAgencyMemberRunsATeam):
            await service.add_member(
                "agency-2",
                AgencyMember(member_kind=MemberKind.USER, member_id="user-7"),
                _caller(),
            )

        teams.remove_member.assert_not_awaited()

    async def test_an_assistant_record_is_never_a_manager(
        self, service: AgencyService, teams: AsyncMock
    ) -> None:
        """``manager_user_id`` names an *account*, so a record cannot match it.

        Notes:
            The identifiers live in different spaces, and comparing them without
            the kind check would refuse an assistant whose record identifier
            happened to equal a manager's account identifier.
        """
        teams.team_for_member.return_value = _team("team-1", "agency-1", "hca-1")

        await service.add_member(
            "agency-2",
            AgencyMember(member_kind=MemberKind.HCA, member_id="hca-1"),
            _caller(),
        )

        teams.remove_member.assert_awaited_once()
