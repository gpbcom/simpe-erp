from __future__ import annotations

# Standard library imports
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.enums import MemberKind, UserRole
from models.organisation.team.team import Team
from service.organisation.teams import TeamService


def _team(team_id: str, name: str = "Équipe Est") -> Team:
    """Build a stored team.

    Args:
        team_id (str): Its identifier.
        name (str): What it is called.

    Returns:
        Team: The team.
    """
    return Team(
        id=team_id,
        company_id="company-1",
        agency_id="agency-1",
        name=name,
        manager_user_id="user-1",
    )


def _caller(role: UserRole = UserRole.MANAGER, hca_id: str | None = None) -> User:
    """Build the account doing the reading.

    Args:
        role (UserRole): The role it holds.
        hca_id (str | None): The assistant record it is bound to, if any.

    Returns:
        User: The account.
    """
    return User(
        id="user-1",
        email="marc@simple-erp.fr",
        full_name="Marc Dubois",
        hashed_password="x" * 20,
        role=role,
        company_id="company-1",
        hca_id=hca_id,
    )


@pytest.fixture
def teams() -> AsyncMock:
    """Return a stubbed team store.

    Returns:
        AsyncMock: The store double.
    """
    stub = AsyncMock()
    stub.list.return_value = [_team("team-1"), _team("team-2", "Équipe Ouest")]
    stub.list_member_ids.return_value = []
    stub.team_for_member.return_value = None
    return stub


@pytest.fixture
def quotes() -> AsyncMock:
    """Return a stubbed quote store.

    Returns:
        AsyncMock: The store double.
    """
    stub = AsyncMock()
    stub.customer_ids_for_teams.return_value = []
    return stub


@pytest.fixture
def service(teams: AsyncMock, quotes: AsyncMock) -> TeamService:
    """Return the service under test.

    Args:
        teams (AsyncMock): The team store.
        quotes (AsyncMock): The quote store.

    Returns:
        TeamService: The service.
    """
    return TeamService(
        teams=teams,
        agencies=AsyncMock(),
        users=AsyncMock(),
        quotes=quotes,
        logger=MagicMock(),
    )


class TestWhichTeamsACallerMayRead:
    """Tests for the one definition every narrowed screen is built on."""

    async def test_an_administrator_is_unscoped(self, service: TeamService) -> None:
        """``None`` means every team, and is not the same as an empty list."""
        assert await service.readable_team_ids(_caller(UserRole.ADMIN)) is None

    async def test_a_manager_sees_the_teams_they_run(
        self, service: TeamService, teams: AsyncMock
    ) -> None:
        """Their narrowing is a list, and the store is asked for it by name."""
        assert await service.readable_team_ids(_caller()) == ["team-1", "team-2"]
        assert teams.list.await_args.kwargs["manager_user_id"] == "user-1"

    async def test_a_manager_who_runs_nothing_sees_nothing(
        self, service: TeamService, teams: AsyncMock
    ) -> None:
        """The empty list, and it must never be read as "no filter".

        Notes:
            This is the case the whole ``None``-versus-``[]`` distinction exists
            for. Code treating the empty list as falsy — the natural reading —
            would hand a manager who runs no team the entire company.
        """
        teams.list.return_value = []
        assert await service.readable_team_ids(_caller()) == []

    async def test_an_assistant_sees_the_team_they_are_on(
        self, service: TeamService, teams: AsyncMock
    ) -> None:
        """One team, found through their assistant record."""
        teams.team_for_member.return_value = _team("team-9")
        caller = _caller(UserRole.HCA, hca_id="hca-1")

        assert await service.readable_team_ids(caller) == ["team-9"]
        assert teams.team_for_member.await_args.args == (MemberKind.HCA, "hca-1")

    async def test_an_assistant_on_no_team_sees_nothing(
        self, service: TeamService
    ) -> None:
        """An empty list, not every team."""
        caller = _caller(UserRole.HCA, hca_id="hca-1")
        assert await service.readable_team_ids(caller) == []

    async def test_a_household_account_sees_nothing(self, service: TeamService) -> None:
        """The defensive floor, and it must be empty rather than unscoped.

        Notes:
            An assistant account cannot exist without a record — the model
            refuses to build one — so the only caller that reaches this branch
            is a household, whose own portal is elsewhere. It answers ``[]``
            because the alternative reading of "nothing to resolve them by" is
            "no restriction", which is the whole company.
        """
        household = User(
            id="user-9",
            email="marie@example.fr",
            full_name="Marie Durand",
            hashed_password="x" * 20,
            role=UserRole.CUSTOMER,
            company_id="company-1",
            customer_id="customer-1",
        )
        assert await service.readable_team_ids(household) == []


class TestWhichAssistantsACallerMayRead:
    """Tests for the workforce projection of the same rule."""

    async def test_an_administrator_is_unscoped(self, service: TeamService) -> None:
        """``None`` travels unchanged, so the statement adds no filter."""
        assert await service.readable_hca_ids(_caller(UserRole.ADMIN)) is None

    async def test_a_manager_sees_the_members_of_their_teams(
        self, service: TeamService, teams: AsyncMock
    ) -> None:
        """The union across the teams they run, deterministically ordered."""
        teams.list_member_ids.side_effect = [["hca-2"], ["hca-1"]]

        assert await service.readable_hca_ids(_caller()) == ["hca-1", "hca-2"]

    async def test_only_assistant_records_are_collected(
        self, service: TeamService, teams: AsyncMock
    ) -> None:
        """A manager on a team as an *account* has no record to appear as."""
        await service.readable_hca_ids(_caller())

        kinds = {call.args[1] for call in teams.list_member_ids.await_args_list}
        assert kinds == {MemberKind.HCA}

    async def test_a_manager_with_empty_teams_sees_nobody(
        self, service: TeamService
    ) -> None:
        """Empty, not unscoped — the same trap one level down."""
        assert await service.readable_hca_ids(_caller()) == []


class TestWhichHouseholdsACallerMayRead:
    """Tests for the customer projection of the same rule."""

    async def test_an_administrator_is_unscoped(self, service: TeamService) -> None:
        """The whole book, expressed as ``None``."""
        assert await service.readable_customer_ids(_caller(UserRole.ADMIN)) is None

    async def test_a_manager_sees_the_households_their_teams_quoted(
        self, service: TeamService, quotes: AsyncMock
    ) -> None:
        """Read off the quotes, so a prospect never planned is still theirs.

        Notes:
            Deriving the scope from the calendar instead would hide exactly the
            households a manager most needs to see: the ones waiting on a
            decision.
        """
        quotes.customer_ids_for_teams.return_value = ["customer-1"]

        assert await service.readable_customer_ids(_caller()) == ["customer-1"]
        assert quotes.customer_ids_for_teams.await_args.args == (["team-1", "team-2"],)

    async def test_a_manager_with_no_quoted_household_sees_none(
        self, service: TeamService
    ) -> None:
        """Empty, not unscoped."""
        assert await service.readable_customer_ids(_caller()) == []
