from __future__ import annotations

# Standard library imports
from datetime import timedelta
from typing import List

# Third-party imports
import pytest

# First-party imports
from models.configuration.planning_config import PlanningConfig
from models.people.hca import Hca
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)
from models.planning.planning_run.planning_solution import PlanningSolution

# Local imports
from tests.planning_scenarios.builder import ScenarioBuilder


@pytest.fixture
def config() -> PlanningConfig:
    """Return a planning configuration with a short solver budget.

    Returns:
        PlanningConfig: Enough for instances of a handful of visits.
    """
    return PlanningConfig(
        solver_time_limit_seconds=30.0,
        solver_deterministic_budget=4.0,
        solver_workers=1,
    )


def _week(build: ScenarioBuilder, days: int) -> List[InterventionRequirement]:
    """Return one visit a day for several consecutive days.

    Args:
        build (ScenarioBuilder): The fixture builder.
        days (int): How many days to cover.

    Returns:
        List[InterventionRequirement]: The work.
    """
    return [
        build.requirement(
            f"req-{index}",
            day=ScenarioBuilder.MONDAY + timedelta(days=index),
            window=index % 2,
        )
        for index in range(days)
    ]


def _solve(
    config: PlanningConfig,
    requirements: List[InterventionRequirement],
    assistants: List[Hca],
) -> PlanningSolution:
    """Solve one instance through the public entry points.

    Args:
        config (PlanningConfig): The planning rules.
        requirements (List[InterventionRequirement]): The work.
        assistants (List[Hca]): The workforce.

    Returns:
        PlanningSolution: What the solver produced.
    """
    build = ScenarioBuilder()
    service = build.service(config)
    service.build_travel(assistants, requirements)
    return service.solve(requirements, assistants, build.settings())


class TestThePeriodIsTheSumOfItsDays:
    """Tests that solving day by day is an exact decomposition.

    Notes:
        A period's model has no constraint linking one day to another: a
        requirement belongs to exactly one day, ``start`` and ``end`` are
        minutes from midnight, the customer no-overlap is keyed by
        ``(customer, day)``, and no-overlap, lunch and travel are all built
        per (assistant, day). The objective is a plain sum. Solving the days
        apart therefore returns the same plan, not merely a similar one.

        **These are the tests that would catch a weekly constraint being
        added.** An hours cap, a rest period or a fairness term would each
        make the decomposition wrong — and wrong quietly, by returning worse
        plans rather than by failing.
    """

    def test_each_day_of_a_week_is_planned(self, config: PlanningConfig) -> None:
        """Work spread over five days is all placed.

        Args:
            config (PlanningConfig): The planning rules.
        """
        build = ScenarioBuilder()
        work = _week(build, 5)

        solution = _solve(config, work, [build.assistant()])

        assert solution.unassigned_requirement_ids == []
        assert len(solution.assignments) == 5

    def test_the_travel_is_the_sum_of_the_days(self, config: PlanningConfig) -> None:
        """A period's travel is what its days cost, added up.

        Args:
            config (PlanningConfig): The planning rules.

        Notes:
            The arithmetic that makes the decomposition exact, asserted
            directly: if merging ever double-counted a home leg or dropped
            one, this is where it would show.
        """
        build = ScenarioBuilder()
        staff = [build.assistant()]
        work = _week(build, 3)

        whole = _solve(config, work, staff)
        apart = sum(_solve(config, [item], staff).total_travel_minutes for item in work)

        assert whole.total_travel_minutes == apart

    def test_the_same_hour_on_two_days_is_two_slots(
        self, config: PlanningConfig
    ) -> None:
        """One assistant can work 09:00 on Monday and 09:00 on Tuesday.

        Args:
            config (PlanningConfig): The planning rules.

        Notes:
            ``start`` and ``end`` carry no day offset, which is safe only
            because every no-overlap set is day-scoped. A decomposition that
            merged two days, or a merge that shared a resource across them,
            fails here and almost nowhere else: the two would be forced to
            take turns and the second would land in the afternoon or not at
            all.

            Asserted as "both inside the same morning window" rather than
            "both at 09:00". They start a few minutes apart because each is
            reached by a different drive from home, and pinning the exact
            minute would be asserting the travel estimate rather than the
            day-scoping this test is about.
        """
        build = ScenarioBuilder()
        monday = build.requirement("req-1", day=ScenarioBuilder.MONDAY, window=0)
        tuesday = build.requirement(
            "req-2", day=ScenarioBuilder.MONDAY + timedelta(days=1), window=0
        )

        solution = _solve(config, [monday, tuesday], [build.assistant()])

        assert solution.unassigned_requirement_ids == []
        assert len(solution.assignments) == 2
        for placed in solution.assignments:
            assert 9 * 60 <= placed.start_minute
            assert placed.end_minute <= 11 * 60

    def test_one_impossible_day_fails_the_whole_period(
        self, config: PlanningConfig
    ) -> None:
        """A period is refused as a whole, however good its other days.

        Args:
            config (PlanningConfig): The planning rules.

        Notes:
            The all-or-nothing gate is over the period, not the day, and the
            status has to survive the merge: ``INFEASIBLE`` is a proof that
            earns "the constraints contradict each other", where a search
            that merely stopped may only say "raise the budget".
        """
        build = ScenarioBuilder()
        good = build.requirement("req-1", day=ScenarioBuilder.MONDAY)
        outside = build.requirement(
            "req-2", day=ScenarioBuilder.MONDAY + timedelta(days=1)
        ).model_copy(
            update={
                "window_start_minute": 6 * 60,
                "window_end_minute": 8 * 60,
                "duration_minutes": 60,
            }
        )

        solution = _solve(config, [good, outside], [build.assistant()])

        assert solution.is_feasible is False
        assert solution.status_name == "INFEASIBLE"


class TestSolvingTheDaysAtOnce:
    """Tests that running the days concurrently changes nothing.

    Notes:
        Concurrency is the one step of this work that can turn a
        deterministic bug into an intermittent one, so what it must prove is
        not that it is faster but that it is *identical*. Each day is solved
        on its own shallow copy of the service, because the model is built on
        instance attributes and two days sharing one would overwrite each
        other's half-built model.
    """

    @pytest.mark.parametrize("concurrency", [1, 2, 8])
    async def test_the_answer_does_not_depend_on_how_many_days_run_at_once(
        self, concurrency: int
    ) -> None:
        """One day at a time and eight at a time give the same plan.

        Args:
            concurrency (int): How many days to solve simultaneously.
        """
        build = ScenarioBuilder()
        staff = [build.assistant("hca-1"), build.assistant("hca-2")]
        work = _week(build, 5)
        config = PlanningConfig(
            solver_time_limit_seconds=30.0,
            solver_deterministic_budget=4.0,
            solver_workers=1,
            solver_day_concurrency=concurrency,
        )
        service = build.service(config)
        service.build_travel(staff, work)

        solution = await service.solve_period(work, staff, build.settings())

        assert solution.unassigned_requirement_ids == []
        assert (
            solution.total_travel_minutes
            == _solve(config, work, staff).total_travel_minutes
        )

    async def test_an_empty_period_needs_no_threads(self) -> None:
        """Nothing to plan is answered without dispatching anything."""
        build = ScenarioBuilder()
        service = build.service(PlanningConfig())

        solution = await service.solve_period([], [build.assistant()], build.settings())

        assert solution.status_name == "EMPTY"
