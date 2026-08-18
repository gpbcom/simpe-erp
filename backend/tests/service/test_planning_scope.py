from __future__ import annotations

# Standard library imports
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.configuration.planning_config import PlanningConfig
from models.enums import PlanningRunStatus, UserRole
from models.organisation.team.team import Team
from models.planning.planning_run import PlanningRun
from service.planning.exceptions import (
    MTPlanningForbidden,
    MTPlanningScopeForbidden,
    MTPlanningTeamForbidden,
)
from service.planning.plannings import PlanningService

MONDAY = "2026-08-17"
SUNDAY = "2026-08-23"


def _team(team_id: str, agency_id: str = "agency-1") -> Team:
    """Build a stored team at a site.

    Args:
        team_id (str): Its identifier.
        agency_id (str): The site it works from.

    Returns:
        Team: The team.
    """
    return Team(
        id=team_id,
        company_id="company-1",
        agency_id=agency_id,
        name=f"Équipe {team_id}",
        manager_user_id="user-9",
    )


def _caller(role: UserRole = UserRole.MANAGER) -> User:
    """Build the account asking for a computation.

    Args:
        role (UserRole): The role it holds.

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
    )


def _run(team_id: str) -> PlanningRun:
    """Build a finished run of one team.

    Args:
        team_id (str): The team it rebuilt.

    Returns:
        PlanningRun: The run.
    """
    return PlanningRun(
        id="run-1",
        status=PlanningRunStatus.SUCCEEDED,
        company_id="company-1",
        team_id=team_id,
        requested_by="user-1",
        period_start=MONDAY,
        period_end=SUNDAY,
    )


@pytest.fixture
def teams() -> AsyncMock:
    """Return a stubbed team service.

    Returns:
        AsyncMock: The double, unscoped by default — an administrator.
    """
    stub = AsyncMock()
    stub.readable_team_ids.return_value = None
    stub.teams = AsyncMock()
    stub.teams.list.return_value = [_team("team-1"), _team("team-2", "agency-2")]
    return stub


@pytest.fixture
def runs() -> AsyncMock:
    """Return a stubbed run store.

    Returns:
        AsyncMock: The double.
    """
    stub = AsyncMock()
    stub.list.return_value = [_run("team-1")]
    stub.get.return_value = _run("team-1")
    return stub


@pytest.fixture
def service(teams: AsyncMock, runs: AsyncMock) -> PlanningService:
    """Return the service under test.

    Args:
        teams (AsyncMock): The team-service double.
        runs (AsyncMock): The run-store double.

    Returns:
        PlanningService: The service.
    """
    return PlanningService(
        runs=runs,
        interventions=AsyncMock(),
        quotes=AsyncMock(),
        customers=AsyncMock(),
        hcas=AsyncMock(),
        types=AsyncMock(),
        settings=AsyncMock(),
        teams=teams,
        config=PlanningConfig(),
        logger=MagicMock(),
    )


class TestTheScopeOfAComputation:
    """Tests for which teams a request to compute a planning covers."""

    async def test_naming_a_team_plans_that_team(
        self, service: PlanningService
    ) -> None:
        """The narrowest scope, and the one a manager uses most."""
        assert await service.teams_to_plan(_caller(), "team-1") == ["team-1"]

    async def test_naming_a_site_plans_every_team_of_it(
        self, service: PlanningService, teams: AsyncMock
    ) -> None:
        """The site scope the requirement asks for, beside the team one."""
        teams.teams.list.return_value = [_team("team-1"), _team("team-3")]

        planned = await service.teams_to_plan(_caller(UserRole.ADMIN), None, "agency-1")

        assert planned == ["team-1", "team-3"]
        assert teams.teams.list.await_args.kwargs["agency_id"] == "agency-1"

    async def test_naming_nothing_plans_the_whole_company(
        self, service: PlanningService
    ) -> None:
        """An administrator's fan-out over every team there is."""
        planned = await service.teams_to_plan(_caller(UserRole.ADMIN))

        assert planned == ["team-1", "team-2"]

    async def test_a_manager_may_not_plan_the_whole_company(
        self, service: PlanningService, teams: AsyncMock
    ) -> None:
        """**Company-wide is an administrator's act.**

        Notes:
            Refused rather than quietly narrowed to their own teams: being told
            the company had been re-planned when one team was would be worse
            than the refusal, and the message names the two scopes they may use.
        """
        teams.readable_team_ids.return_value = ["team-1"]

        with pytest.raises(MTPlanningScopeForbidden):
            await service.teams_to_plan(_caller())

    async def test_a_manager_may_not_plan_a_colleagues_team(
        self, service: PlanningService, teams: AsyncMock
    ) -> None:
        """A run rewrites the named team's week, so naming is the whole risk."""
        teams.readable_team_ids.return_value = ["team-1"]

        with pytest.raises(MTPlanningTeamForbidden):
            await service.teams_to_plan(_caller(), "team-2")

    async def test_a_site_gives_a_manager_only_their_own_teams(
        self, service: PlanningService, teams: AsyncMock
    ) -> None:
        """**The intersection, not the site's roster.**

        Notes:
            Handing a manager every team at a site would make a branch office a
            way to rebuild a colleague's week without ever naming their team.
        """
        teams.readable_team_ids.return_value = ["team-1"]
        teams.teams.list.return_value = [_team("team-1"), _team("team-9")]

        planned = await service.teams_to_plan(_caller(), None, "agency-1")

        assert planned == ["team-1"]

    async def test_a_site_where_they_run_nothing_is_empty_not_refused(
        self, service: PlanningService, teams: AsyncMock
    ) -> None:
        """An honest answer to "plan my teams here", saying nothing about it."""
        teams.readable_team_ids.return_value = ["team-1"]
        teams.teams.list.return_value = [_team("team-9")]

        assert await service.teams_to_plan(_caller(), None, "agency-2") == []

    async def test_a_named_team_wins_over_a_named_site(
        self, service: PlanningService
    ) -> None:
        """The narrower of the two, so honouring it can only plan less."""
        planned = await service.teams_to_plan(
            _caller(UserRole.ADMIN), "team-1", "agency-2"
        )

        assert planned == ["team-1"]

    async def test_an_administrator_with_no_team_gets_nothing_to_plan(
        self, service: PlanningService, teams: AsyncMock
    ) -> None:
        """A company that has not formed a team is data, not a mistake."""
        teams.teams.list.return_value = []

        assert await service.teams_to_plan(_caller(UserRole.ADMIN)) == []


class TestReadingTheRuns:
    """Tests for the listing and the polling the screen lives on."""

    async def test_a_manager_lists_only_their_teams_runs(
        self, service: PlanningService, teams: AsyncMock, runs: AsyncMock
    ) -> None:
        """**Narrowed in the statement, never after the fact.**

        Notes:
            A page cut down after it was read has already read records the
            caller may not see.
        """
        teams.readable_team_ids.return_value = ["team-1"]

        await service.list_runs(_caller())

        assert runs.list.await_args.args == ("company-1", ["team-1"])

    async def test_an_administrator_lists_every_team_of_their_company(
        self, service: PlanningService, runs: AsyncMock
    ) -> None:
        """``None`` is every team. The company is still the boundary."""
        await service.list_runs(_caller(UserRole.ADMIN))

        assert runs.list.await_args.args == ("company-1", None)

    async def test_polling_a_run_of_their_team_works(
        self, service: PlanningService, teams: AsyncMock
    ) -> None:
        """The ordinary case: the run they just started."""
        teams.readable_team_ids.return_value = ["team-1"]

        assert (await service.run("run-1", _caller())).team_id == "team-1"

    async def test_polling_a_colleagues_run_is_refused(
        self, service: PlanningService, teams: AsyncMock, runs: AsyncMock
    ) -> None:
        """**Every manager holds real run identifiers.**

        Notes:
            Starting a run hands the caller one, so the identifier space is not
            a secret. Without this check a manager could poll a colleague's and
            learn how much of that team's week would not fit.
        """
        teams.readable_team_ids.return_value = ["team-1"]
        runs.get.return_value = _run("team-2")

        with pytest.raises(MTPlanningForbidden):
            await service.run("run-1", _caller())
