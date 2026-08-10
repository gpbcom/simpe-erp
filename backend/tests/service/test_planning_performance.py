from __future__ import annotations

# Standard library imports
import time

# Third-party imports
import pytest

# First-party imports
from models.configuration.app_config import AppConfig
from models.configuration.planning_config import PlanningConfig

# Local imports
from tests.planning_scenarios.workload import WorkloadGenerator

#: The agreed acceptance criterion for a week, in seconds.
BUDGET_SECONDS = 60.0

#: The workforce every case is solved over.
ASSISTANTS = 12

#: A week at roughly forty percent of the workforce's capacity. Loose enough
#: that it was never the problem; it is here as a guard against a regression
#: that only shows up on easy input.
EASY_VISITS = 95

#: A week at roughly sixty percent of capacity. **This is the case that
#: represented the reported problem.** Before the per-day decomposition it ran
#: past a ten-minute wall-clock net without proving anything — which is what
#: "tens of minutes" looks like from the inside. It now completes in under a
#: minute with every visit placed.
HARD_VISITS = 150

DAYS = 5


@pytest.mark.performance
@pytest.mark.timeout(1200)
class TestAWeekSolvesQuickly:
    """Times the solver on weeks the size of real ones.

    Notes:
        **Deselected by default** — see ``addopts`` in ``pyproject.toml`` —
        because these are minutes of CPU against the milliseconds the rest of
        the suite costs. Run them with ``-m performance``.

        Both instances come from :class:`WorkloadGenerator`, which derives the
        work from a schedule it has already laid down, so a feasible plan
        provably exists. That is what makes "visits went unplaced" mean the
        solver fell short of an answer known to exist, rather than the week
        being impossible.

        **Two sizes, because one was not enough.** The reported problem is a
        95-visit week that runs for tens of minutes, but a generated 95-visit
        week solves to proven optimality in about fifteen seconds — the
        generated one is simply looser than the real one. Measuring only that
        size would have declared victory against a problem nobody has. The
        150-visit case is the one that actually reproduces the difficulty, and
        it is the one the refactor has to move.
    """

    @pytest.fixture
    def config(self) -> PlanningConfig:
        """Return the solver settings an operator actually runs.

        Returns:
            PlanningConfig: What ``conf/app.yaml`` ships, with the wall-clock
            safety net pulled down to ninety seconds.

        Notes:
            **Read from the shipped file rather than from the model
            defaults.** The two have disagreed before — the defaults said one
            search worker while every ``conf/app*.yaml`` said eight — and a
            fixture built from the bare defaults then measures a
            configuration nobody deploys. It measured that one six times
            slower than the real thing.

            Loaded rather than copied for the same reason the sizing tables
            live beside the settings they describe: a number repeated here
            would be a second copy to keep in step, and the failure when it
            drifted would look like a performance regression rather than a
            stale test.

            The net is the only thing standing between a failing measurement
            and a ten-minute test. At ninety seconds a run that cannot meet
            the sixty-second criterion still fails promptly and reports the
            figure it reached, which is the number worth having.
        """
        shipped = AppConfig.load().planning
        return shipped.model_copy(update={"solver_time_limit_seconds": 90.0})

    async def _solve(self, config: PlanningConfig, visits: int) -> float:
        """Solve one generated week and return how long it took.

        Args:
            config (PlanningConfig): The solver settings.
            visits (int): How much work to generate.

        Returns:
            float: Seconds spent solving.

        Notes:
            Times ``solve_period``, not ``solve``. The two return the same
            plan, but only the first is what a planning run actually calls —
            it puts each day on its own thread. Timing the synchronous entry
            point would measure a path nobody takes and report a week as
            several times slower than an operator sees it.
        """
        generator = WorkloadGenerator()
        staff = generator.workforce(ASSISTANTS)
        work = generator.week(staff, visits, days=DAYS)
        service = generator.build.service(config)
        service.build_travel(staff, work)

        started = time.monotonic()
        await service.solve_period(work, staff, generator.build.settings())
        return time.monotonic() - started

    async def test_a_loose_week_is_planned_in_full(
        self, config: PlanningConfig
    ) -> None:
        """Nothing is left out of a week the workforce can comfortably do.

        Args:
            config (PlanningConfig): The solver settings.
        """
        generator = WorkloadGenerator()
        staff = generator.workforce(ASSISTANTS)
        work = generator.week(staff, EASY_VISITS, days=DAYS)
        service = generator.build.service(config)
        service.build_travel(staff, work)

        solution = await service.solve_period(
            work, staff, generator.build.settings()
        )

        assert solution.is_feasible
        assert solution.unassigned_requirement_ids == []

    async def test_a_loose_week_solves_inside_the_budget(
        self, config: PlanningConfig
    ) -> None:
        """The size that already passes, kept passing.

        Args:
            config (PlanningConfig): The solver settings.
        """
        elapsed = await self._solve(config, EASY_VISITS)

        assert elapsed < BUDGET_SECONDS, (
            f"{EASY_VISITS} visits over {DAYS} days took {elapsed:.1f}s "
            f"against a {BUDGET_SECONDS:.0f}s budget."
        )

    async def test_a_tight_week_solves_inside_the_budget(
        self, config: PlanningConfig
    ) -> None:
        """The size that reproduces the reported problem.

        Args:
            config (PlanningConfig): The solver settings.

        Notes:
            Written while it still failed, and kept because the number in its
            message is the whole point: it was 91.8s against a single model,
            and the same measurement after each step of the refactor is what
            showed which step actually moved it. Decomposition alone did not —
            a budget became per-day and the week briefly got *slower*.
        """
        elapsed = await self._solve(config, HARD_VISITS)

        assert elapsed < BUDGET_SECONDS, (
            f"{HARD_VISITS} visits over {DAYS} days took {elapsed:.1f}s "
            f"against a {BUDGET_SECONDS:.0f}s budget."
        )
