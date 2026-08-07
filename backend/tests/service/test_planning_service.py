from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import List, Optional
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.configuration.planning_config import PlanningConfig
from models.enums import (
    ContractType,
    InterventionStatus,
    PlanningRunStatus,
    UserRole,
)
from models.people.hca import Hca
from models.planning.intervention import Intervention
from models.planning.planning_run import PlanningRun
from models.settings.planning_settings import PlanningSettings
from service.planning.exceptions import MTPlanningForbidden, MTPlanningRunNotFound
from service.planning.plannings import PlanningService
from storage.repositories.planning.planning_settings import PlanningSettingsRepository

MONDAY = date(2026, 8, 3)
SUNDAY = date(2026, 8, 9)


def _hca(hca_id: str = "hca-1", first_name: str = "Luc") -> Hca:
    """Build an assistant.

    Args:
        hca_id (str): The identifier to assign.
        first_name (str): Their given name.

    Returns:
        Hca: The assistant.
    """
    return Hca(
        company_id="company-1",
        id=hca_id,
        first_name=first_name,
        last_name="Martin",
        phone_number="+33698765432",
        email=f"{hca_id}@example.com",
        address={
            "street": "5 avenue de la Gare",
            "postal_code": "75012",
            "city": "Paris",
            "latitude": 48.8443,
            "longitude": 2.3735,
        },
        contract_type=ContractType.CDI,
    )


def _user(role: UserRole, hca_id: Optional[str] = None) -> User:
    """Build an authenticated account.

    Args:
        role (UserRole): What the account may do.
        hca_id (Optional[str]): The assistant record it is bound to, if any.

    Returns:
        User: The account.
    """
    return User(
        company_id="company-1",
        id=f"user-{role.value}",
        email=f"{role.value}@example.com",
        full_name=f"Test {role.value.title()}",
        hashed_password="$2b$12$" + "a" * 53,
        role=role,
        hca_id=hca_id,
    )


def _visit(hca_id: str = "hca-1") -> Intervention:
    """Build a scheduled visit.

    Args:
        hca_id (str): The assistant performing it.

    Returns:
        Intervention: The visit.
    """
    return Intervention(
        company_id="company-1",
        id="visit-1",
        planning_run_id="run-1",
        name="Toilette matin",
        intervention_type_id="type-1",
        quote_line_id="line-1",
        hca_id=hca_id,
        hca_full_name="Luc Martin",
        customer_id="customer-1",
        day=MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        address={
            "street": "12 rue de Rivoli",
            "postal_code": "75004",
            "city": "Paris",
            "latitude": 48.8566,
            "longitude": 2.3522,
        },
        status=InterventionStatus.PLANNED,
    )


@pytest.fixture
def runs() -> AsyncMock:
    """Return a stand-in run repository.

    Returns:
        AsyncMock: The repository double.
    """
    repository = AsyncMock()
    repository.get.return_value = None
    # The real claim is a conditional update that hands back the run it won,
    # now RUNNING. Returning None would mean "another worker holds it", which
    # is a case these tests set up explicitly when they want it.
    repository.claim.side_effect = lambda run_id, started_at: PlanningRun(
        company_id="company-1",
        id=run_id,
        status=PlanningRunStatus.RUNNING,
        requested_by="admin-1",
        period_start=MONDAY,
        period_end=SUNDAY,
        started_at=started_at,
    )
    return repository


@pytest.fixture
def interventions() -> AsyncMock:
    """Return a stand-in intervention repository.

    Returns:
        AsyncMock: The repository double, holding one visit for ``hca-1``.
    """
    repository = AsyncMock()
    repository.list_for_hca.return_value = [_visit()]
    repository.list_hca_ids_for_period.return_value = ["hca-1", "hca-2"]
    return repository


@pytest.fixture
def hcas() -> AsyncMock:
    """Return a stand-in assistant repository.

    Returns:
        AsyncMock: The repository double, resolving any identifier.
    """
    repository = AsyncMock()
    repository.get.return_value = _hca()
    return repository


@pytest.fixture
def types() -> AsyncMock:
    """Return a stand-in catalogue repository.

    Returns:
        AsyncMock: The repository double, resolving no catalogue entry.

    Notes:
        An empty catalogue is the right default here: a line whose entry is not
        loaded is planned as requiring no qualification, which is the state
        every one of these lifecycle tests is written against.
    """
    repository = AsyncMock()
    repository.get_many.return_value = {}
    return repository


@pytest.fixture
def planning_settings() -> AsyncMock:
    """Return a stand-in settings store with a wide-open radius.

    Returns:
        AsyncMock: The settings-repository double.
    """
    repository = AsyncMock(spec=PlanningSettingsRepository)
    repository.get.return_value = PlanningSettings(
        max_intervention_radius_km=200.0, lunch_break_minutes=60
    )
    return repository


@pytest.fixture
def service(
    runs: AsyncMock,
    interventions: AsyncMock,
    hcas: AsyncMock,
    types: AsyncMock,
    planning_settings: AsyncMock,
) -> PlanningService:
    """Return a planning service over stand-in repositories.

    Args:
        runs (AsyncMock): The run repository double.
        interventions (AsyncMock): The intervention repository double.
        hcas (AsyncMock): The assistant repository double.
        types (AsyncMock): The catalogue repository double.
        planning_settings (AsyncMock): The settings-repository double.

    Returns:
        PlanningService: The service under test.
    """
    return PlanningService(
        runs=runs,
        interventions=interventions,
        quotes=AsyncMock(),
        customers=AsyncMock(),
        hcas=hcas,
        types=types,
        settings=planning_settings,
        config=PlanningConfig(),
    )


class TestPlanningConfidentiality:
    """Tests for the rule that an assistant sees only their own diary."""

    # ------------------------------------------------------------------ #
    #  The row-level check
    # ------------------------------------------------------------------ #

    async def test_an_assistant_may_read_their_own_planning(
        self, service: PlanningService
    ) -> None:
        """The ordinary case still works."""
        planning = await service.planning_for(
            "hca-1", _user(UserRole.HCA, "hca-1"), MONDAY, SUNDAY
        )

        assert planning.hca_id == "hca-1"
        assert len(planning.interventions) == 1

    async def test_an_assistant_cannot_read_another_assistants_planning(
        self, service: PlanningService
    ) -> None:
        """Passing a colleague's identifier is refused.

        Notes:
            **This is the test the whole rule rests on.** A route guard proves
            only that the caller is an assistant; nothing at the routing layer
            stops assistant A putting assistant B's identifier in the path. The
            comparison can only be made here, against the caller's own record.
        """
        with pytest.raises(MTPlanningForbidden):
            await service.planning_for(
                "hca-2", _user(UserRole.HCA, "hca-1"), MONDAY, SUNDAY
            )

    async def test_a_refused_read_never_touches_the_store(
        self, service: PlanningService, interventions: AsyncMock
    ) -> None:
        """The check happens before the query, not after it.

        Notes:
            Checking after reading would still return 403, but the rows would
            have been loaded — and anything that later logs or caches the
            query result would hold data the caller was never entitled to.
        """
        with pytest.raises(MTPlanningForbidden):
            await service.planning_for(
                "hca-2", _user(UserRole.HCA, "hca-1"), MONDAY, SUNDAY
            )

        interventions.list_for_hca.assert_not_called()

    async def test_an_assistant_account_with_no_record_is_refused(
        self, service: PlanningService
    ) -> None:
        """An assistant account not bound to an assistant sees nothing.

        Notes:
            Such an account cannot normally be built — :class:`User` refuses it
            outright, which is the primary defence. It is forced into existence
            here with ``model_construct`` to prove the service does not fall
            back on "unbound means unrestricted" if one ever reaches it, say
            from a token minted before the invariant existed.
        """
        unbound = User.model_construct(
            id="user-hca",
            email="hca@example.com",
            full_name="Test Hca",
            hashed_password="$2b$12$" + "a" * 53,
            role=UserRole.HCA,
            hca_id=None,
        )

        with pytest.raises(MTPlanningForbidden):
            await service.planning_for("hca-1", unbound, MONDAY, SUNDAY)

    @pytest.mark.parametrize(
        "role",
        [
            pytest.param(UserRole.MANAGER, id="Allowed - manager"),
            pytest.param(UserRole.ADMIN, id="Allowed - admin"),
        ],
    )
    async def test_a_manager_may_read_any_planning(
        self, service: PlanningService, role: UserRole
    ) -> None:
        """Supervision requires seeing everybody's diary.

        Args:
            service (PlanningService): The service under test.
            role (UserRole): The supervising role to check.
        """
        planning = await service.planning_for("hca-1", _user(role), MONDAY, SUNDAY)

        assert planning.hca_id == "hca-1"

    # ------------------------------------------------------------------ #
    #  Listing every planning
    # ------------------------------------------------------------------ #

    async def test_an_assistant_listing_all_gets_only_their_own(
        self, service: PlanningService
    ) -> None:
        """The list endpoint narrows rather than refusing.

        Notes:
            It is the same screen for both roles. Refusing would be gratuitous
            — what matters is that the narrowed list can only ever contain the
            caller's own diary.
        """
        plannings = await service.all_plannings(
            _user(UserRole.HCA, "hca-1"), MONDAY, SUNDAY
        )

        assert [planning.hca_id for planning in plannings] == ["hca-1"]

    async def test_a_manager_listing_all_gets_every_planning(
        self, service: PlanningService, hcas: AsyncMock
    ) -> None:
        """A manager sees the whole workforce."""
        hcas.get.side_effect = [_hca("hca-1"), _hca("hca-2", "Ana")]

        plannings = await service.all_plannings(_user(UserRole.MANAGER), MONDAY, SUNDAY)

        assert [planning.hca_id for planning in plannings] == ["hca-1", "hca-2"]

    async def test_an_unbound_assistant_listing_all_is_refused(
        self, service: PlanningService
    ) -> None:
        """An assistant account with no record cannot list anything.

        Notes:
            As above, the account is forced into existence rather than built:
            the model already refuses it, and this pins the service's own
            fallback.
        """
        unbound = User.model_construct(
            id="user-hca",
            email="hca@example.com",
            full_name="Test Hca",
            hashed_password="$2b$12$" + "a" * 53,
            role=UserRole.HCA,
            hca_id=None,
        )

        with pytest.raises(MTPlanningForbidden):
            await service.all_plannings(unbound, MONDAY, SUNDAY)


class TestPlanningRunIsScopedToOneAgency:
    """Tests for the rule that a run only ever reads and writes its own agency."""

    async def test_the_run_decides_whose_work_is_scheduled(
        self, service: PlanningService, runs: AsyncMock
    ) -> None:
        """The workload query is asked for the run's agency, not for everybody.

        Notes:
            Unscoped, a run built one agency's week out of every agency's
            accepted work and handed those visits to its own assistants — people
            who have never met the customers and are not insured to attend them.
        """
        runs.get.return_value = PlanningRun(
            company_id="company-2",
            id="run-1",
            status=PlanningRunStatus.PENDING,
            requested_by="admin-1",
            period_start=MONDAY,
            period_end=SUNDAY,
        )
        runs.claim.side_effect = lambda run_id, started_at: runs.get.return_value
        runs.update.side_effect = lambda run: run
        service.quotes.list_schedulable.return_value = []
        service.hcas.list_all.return_value = [_hca()]

        await service.execute_run("run-1")

        assert service.quotes.list_schedulable.await_args.args[0] == "company-2"

    async def test_the_run_decides_whose_calendar_is_rewritten(
        self, service: PlanningService, runs: AsyncMock, interventions: AsyncMock
    ) -> None:
        """The replacement is asked for the run's agency too.

        Notes:
            This is the destructive half. The two have to agree: reading one
            agency's work and clearing another's period would empty a calendar
            and fill it with somebody else's visits.
        """
        runs.get.return_value = PlanningRun(
            company_id="company-2",
            id="run-1",
            status=PlanningRunStatus.PENDING,
            requested_by="admin-1",
            period_start=MONDAY,
            period_end=SUNDAY,
        )
        runs.claim.side_effect = lambda run_id, started_at: runs.get.return_value
        runs.update.side_effect = lambda run: run
        service.quotes.list_schedulable.return_value = []
        service.hcas.list_all.return_value = [_hca()]
        interventions.replace_for_period.return_value = 0

        await service.execute_run("run-1")

        assert interventions.replace_for_period.await_args.args[0] == "company-2"

    async def test_a_requested_run_records_the_agency_that_asked(
        self, service: PlanningService, runs: AsyncMock
    ) -> None:
        """The agency is stored, not resolved from the requester later.

        Notes:
            ``requested_by`` carries no foreign key, so the administrator is
            allowed to be gone by the time a worker picks the run up.
        """
        runs.create.side_effect = lambda run: run.model_copy(update={"id": "run-1"})

        run = await service.request_run("admin-1", "company-2", MONDAY, SUNDAY)

        assert run.company_id == "company-2"


class TestPlanningRunLifecycle:
    """Tests for requesting, polling and failing a run."""

    # ------------------------------------------------------------------ #
    #  Claiming
    # ------------------------------------------------------------------ #

    async def test_a_run_another_worker_holds_is_left_alone(
        self, service: PlanningService, runs: AsyncMock, interventions: AsyncMock
    ) -> None:
        """Losing the claim solves nothing and writes nothing.

        Notes:
            **A message really is handed to two workers.** It is acknowledged
            only once its handler returns, so a worker killed mid-solve leaves
            its run to be redelivered — and the second worker must not solve the
            same period and overwrite the first's plan.
        """
        pending = PlanningRun(
            company_id="company-1",
            id="run-1",
            status=PlanningRunStatus.PENDING,
            requested_by="admin-1",
            period_start=MONDAY,
            period_end=SUNDAY,
        )
        runs.get.return_value = pending
        runs.claim.side_effect = lambda run_id, started_at: None

        finished = await service.execute_run("run-1")

        assert finished is pending
        service.quotes.list_schedulable.assert_not_awaited()
        interventions.replace_for_period.assert_not_awaited()

    async def test_losing_the_claim_is_not_a_failure(
        self, service: PlanningService, runs: AsyncMock
    ) -> None:
        """The run is returned as it stands, not marked failed.

        Notes:
            Recording a failure would put a red run in front of a manager for
            work that is being done correctly by another worker — and, because
            the handler dead-letters what raises, would take the message with
            it.
        """
        runs.get.return_value = PlanningRun(
            company_id="company-1",
            id="run-1",
            status=PlanningRunStatus.RUNNING,
            requested_by="admin-1",
            period_start=MONDAY,
            period_end=SUNDAY,
        )
        runs.claim.side_effect = lambda run_id, started_at: None

        finished = await service.execute_run("run-1")

        assert finished.status is PlanningRunStatus.RUNNING
        runs.update.assert_not_awaited()

    # ------------------------------------------------------------------ #
    #  Requesting
    # ------------------------------------------------------------------ #

    async def test_a_requested_run_starts_pending(
        self, service: PlanningService, runs: AsyncMock
    ) -> None:
        """The run exists before any solving happens.

        Notes:
            This is what makes the 202 honest: the identifier handed back
            already names a stored record, so a client polling immediately
            finds it rather than a 404.
        """
        runs.create.side_effect = lambda run: run.model_copy(update={"id": "run-1"})

        run = await service.request_run("admin-1", "company-1", MONDAY, SUNDAY)

        assert run.status is PlanningRunStatus.PENDING
        assert run.requested_by == "admin-1"

    # ------------------------------------------------------------------ #
    #  Polling
    # ------------------------------------------------------------------ #

    async def test_an_absent_run_is_reported_not_guessed(
        self, service: PlanningService
    ) -> None:
        """Polling an identifier that does not exist raises."""
        with pytest.raises(MTPlanningRunNotFound):
            await service.get_run("nope")

    async def test_executing_an_absent_run_raises(
        self, service: PlanningService
    ) -> None:
        """A background job for a deleted run fails loudly."""
        with pytest.raises(MTPlanningRunNotFound):
            await service.execute_run("nope")

    # ------------------------------------------------------------------ #
    #  Failing
    # ------------------------------------------------------------------ #

    async def test_a_solver_failure_is_recorded_on_the_run(
        self, service: PlanningService, runs: AsyncMock
    ) -> None:
        """A run that blows up ends FAILED with its message, not an exception.

        Notes:
            The caller already holds their 202. An exception raised out of the
            background task would go nowhere and leave the run RUNNING for
            ever, so the failure has to land where the client is looking.
        """
        pending = PlanningRun(
            company_id="company-1",
            id="run-1",
            status=PlanningRunStatus.PENDING,
            requested_by="admin-1",
            period_start=MONDAY,
            period_end=SUNDAY,
        )
        runs.get.return_value = pending
        runs.update.side_effect = lambda run: run
        service.quotes.list_schedulable.side_effect = RuntimeError("database is gone")

        finished = await service.execute_run("run-1")

        assert finished.status is PlanningRunStatus.FAILED
        assert "database is gone" in (finished.error_message or "")

    async def test_a_run_with_nothing_to_plan_succeeds_empty(
        self, service: PlanningService, runs: AsyncMock, interventions: AsyncMock
    ) -> None:
        """No accepted work is an empty plan, not a failure.

        Notes:
            An agency with a quiet week must not see a red run; the distinction
            between "nothing to do" and "could not compute" is exactly what the
            status is for.
        """
        pending = PlanningRun(
            company_id="company-1",
            id="run-1",
            status=PlanningRunStatus.PENDING,
            requested_by="admin-1",
            period_start=MONDAY,
            period_end=SUNDAY,
        )
        runs.get.return_value = pending
        runs.update.side_effect = lambda run: run
        service.quotes.list_schedulable.return_value = []
        service.hcas.list_all.return_value = [_hca()]
        interventions.replace_for_period.return_value = 0

        finished = await service.execute_run("run-1")

        assert finished.status is PlanningRunStatus.SUCCEEDED
        assert finished.scheduled_count == 0

    async def test_the_periods_plan_is_replaced_not_appended(
        self, service: PlanningService, runs: AsyncMock, interventions: AsyncMock
    ) -> None:
        """Re-planning a week swaps its visits rather than duplicating them.

        Notes:
            Appending would double-book every assistant on the second run,
            which is the sort of failure that reaches a customer's front door
            before it reaches a log.
        """
        runs.get.return_value = PlanningRun(
            company_id="company-1",
            id="run-1",
            status=PlanningRunStatus.PENDING,
            requested_by="admin-1",
            period_start=MONDAY,
            period_end=SUNDAY,
        )
        runs.update.side_effect = lambda run: run
        service.quotes.list_schedulable.return_value = []
        service.hcas.list_all.return_value = [_hca()]
        interventions.replace_for_period.return_value = 0

        await service.execute_run("run-1")

        interventions.replace_for_period.assert_awaited_once()
        assert interventions.create.await_count == 0


class TestPlanningReads:
    """Tests for what a diary contains."""

    async def test_a_planning_carries_the_assistants_name(
        self, service: PlanningService
    ) -> None:
        """The diary names who it belongs to, for display."""
        planning = await service.planning_for(
            "hca-1", _user(UserRole.ADMIN), MONDAY, SUNDAY
        )

        assert planning.hca_full_name == "Luc Martin"

    async def test_an_absent_assistant_is_reported(
        self, service: PlanningService, hcas: AsyncMock
    ) -> None:
        """Asking for a diary of somebody who does not exist raises."""
        hcas.get.return_value = None

        with pytest.raises(MTPlanningRunNotFound):
            await service.planning_for("ghost", _user(UserRole.ADMIN), MONDAY, SUNDAY)

    async def test_the_period_is_carried_onto_the_planning(
        self, service: PlanningService
    ) -> None:
        """A diary states the window it covers."""
        planning = await service.planning_for(
            "hca-1", _user(UserRole.MANAGER), MONDAY, SUNDAY
        )

        assert planning.period_start == MONDAY
        assert planning.period_end == SUNDAY

    async def test_the_visits_come_through_unchanged(
        self, service: PlanningService
    ) -> None:
        """What the store holds is what the caller receives."""
        planning = await service.planning_for(
            "hca-1", _user(UserRole.MANAGER), MONDAY, SUNDAY
        )
        visits: List[Intervention] = planning.interventions

        assert visits[0].name == "Toilette matin"
        assert visits[0].start_time == time(9, 0)


class TestPlanningSettingsLifecycle:
    """Tests for the rules a manager reads and changes."""

    @pytest.fixture
    def settings(self) -> AsyncMock:
        """Return a stand-in settings store holding nothing yet.

        Returns:
            AsyncMock: The store, seeding whatever it is handed.
        """
        store = AsyncMock(spec=PlanningSettingsRepository)
        store.get.return_value = None
        store.seed.side_effect = lambda model: model
        store.update.side_effect = lambda model: model
        return store

    @pytest.fixture
    def service(self, settings: AsyncMock) -> PlanningService:
        """Return a planning service over a stand-in settings store.

        Args:
            settings (AsyncMock): The settings store.

        Returns:
            PlanningService: The service under test.
        """
        return PlanningService(
            runs=AsyncMock(),
            interventions=AsyncMock(),
            quotes=AsyncMock(),
            customers=AsyncMock(),
            hcas=AsyncMock(),
            types=AsyncMock(),
            settings=settings,
            config=PlanningConfig(
                day_start_minute=8 * 60,
                day_end_minute=19 * 60,
                lunch_break_minutes=75,
                lunch_window_start_minute=12 * 60,
                lunch_window_end_minute=14 * 60,
                max_intervention_radius_km=25.0,
            ),
        )

    async def test_the_whole_working_day_is_seeded_from_configuration(
        self, service: PlanningService
    ) -> None:
        """A fresh install plans on the deployed hours, not on the defaults.

        Notes:
            All six values are seeded, not just the two that were stored
            before. Seeding a subset would leave a deployment that had set
            ``day_start_minute: 480`` planning from 09:00 anyway — the exact
            failure this feature exists to remove.
        """
        seeded = await service.current_settings()

        assert seeded.day_start_minute == 8 * 60
        assert seeded.day_end_minute == 19 * 60
        assert seeded.lunch_break_minutes == 75
        assert seeded.lunch_window_start_minute == 12 * 60
        assert seeded.lunch_window_end_minute == 14 * 60
        assert seeded.max_intervention_radius_km == 25.0

    async def test_a_stored_row_is_not_reseeded(
        self, service: PlanningService, settings: AsyncMock
    ) -> None:
        """The configuration is a seed, not a fallback.

        Notes:
            Treating the file as a live fallback would let a redeployment
            silently overwrite a manager's decision.
        """
        settings.get.return_value = PlanningSettings(
            max_intervention_radius_km=40.0, day_start_minute=7 * 60
        )
        current = await service.current_settings()

        assert current.day_start_minute == 7 * 60
        settings.seed.assert_not_called()

    async def test_a_change_carries_the_whole_working_day(
        self, service: PlanningService, settings: AsyncMock
    ) -> None:
        """Every field a manager sent reaches the store."""
        updated = await service.update_settings(
            max_intervention_radius_km=35.0,
            day_start_minute=7 * 60 + 30,
            day_end_minute=18 * 60,
            lunch_break_minutes=60,
            lunch_window_start_minute=11 * 60,
            lunch_window_end_minute=13 * 60,
            updated_by="user-1",
        )

        assert updated.day_start_minute == 7 * 60 + 30
        assert updated.day_end_minute == 18 * 60
        assert updated.lunch_window_start_minute == 11 * 60
        assert updated.lunch_window_end_minute == 13 * 60
        assert updated.updated_by == "user-1"
        assert settings.update.await_count == 1

    async def test_a_change_records_who_made_it(self, service: PlanningService) -> None:
        """A day that quietly moved is a question with a name attached."""
        updated = await service.update_settings(
            max_intervention_radius_km=30.0,
            day_start_minute=9 * 60,
            day_end_minute=20 * 60,
            lunch_break_minutes=60,
            lunch_window_start_minute=11 * 60 + 30,
            lunch_window_end_minute=14 * 60 + 30,
            updated_by="manager-7",
        )

        assert updated.updated_by == "manager-7"
        assert updated.updated_at is not None
