from __future__ import annotations

# Standard library imports
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


def _round(build: ScenarioBuilder) -> List[InterventionRequirement]:
    """Return a day of work with more than one sensible ordering.

    Args:
        build (ScenarioBuilder): The fixture builder.

    Returns:
        List[InterventionRequirement]: Four visits across the working day.

    Notes:
        Four visits in four different windows, so the day is comfortably
        placeable but the order they are driven in still costs different
        amounts. A single visit would be optimal however it was solved, and
        would make the optimisation pass untestable.
    """
    return [
        build.requirement(f"req-{index}", window=window)
        for index, window in enumerate((0, 1, 3, 4))
    ]


class TestTheTwoPasses:
    """Tests that a plan is optimised only when it is complete.

    Notes:
        The requirement is "optimise if and only if a feasible plan exists,
        otherwise return the feasible one". Splitting the solve in two is
        what implements it: the first pass minimises only what was left out,
        the second shortens the driving and runs **only** if the first placed
        everything.

        The fallback is the case worth pinning. A short second budget must
        never cost a visit — it costs undriven minutes and says so.
    """

    def test_a_complete_plan_is_optimised(self) -> None:
        """The ordinary case: everything placed, then the rounds shortened."""
        build = ScenarioBuilder()
        config = PlanningConfig(
            solver_time_limit_seconds=30.0,
            solver_deterministic_budget=4.0,
            solver_optimisation_budget=4.0,
            solver_workers=1,
        )

        solution = _solve(config, _round(build), [build.assistant()])

        assert solution.unassigned_requirement_ids == []
        assert solution.is_optimised is True

    def test_a_starved_optimisation_still_returns_a_complete_plan(self) -> None:
        """**The acceptance test for the fallback.**

        Notes:
            The second pass is given the smallest budget the configuration
            permits. What must survive is the plan: every visit still placed,
            the run still usable, and the only casualty the *claim* that the
            driving is minimal.
        """
        build = ScenarioBuilder()
        config = PlanningConfig(
            solver_time_limit_seconds=30.0,
            solver_deterministic_budget=4.0,
            solver_optimisation_budget=0.000001,
            solver_workers=1,
        )

        solution = _solve(config, _round(build), [build.assistant()])

        assert solution.is_feasible is True
        assert solution.unassigned_requirement_ids == []
        assert solution.is_optimised is False

    def test_optimising_never_costs_a_visit(self) -> None:
        """A shorter round is never bought by dropping work.

        Notes:
            The second pass pins ``sum(unassigned) == 0`` before it minimises
            travel, precisely so the solver cannot discover that the shortest
            round is the one that skips the furthest customer. Without that
            pin the objective would happily trade a visit for the drive to
            it.
        """
        build = ScenarioBuilder()
        config = PlanningConfig(
            solver_time_limit_seconds=30.0,
            solver_deterministic_budget=4.0,
            solver_optimisation_budget=4.0,
            solver_workers=1,
        )
        work = _round(build)

        solution = _solve(config, work, [build.assistant()])

        assert len(solution.assignments) == len(work)

    def test_work_that_cannot_be_placed_is_never_optimised(self) -> None:
        """A day that fails does not spend a budget on its driving.

        Notes:
            Both halves matter. The plan is refused as before — that has not
            changed — and ``is_optimised`` stays false rather than being
            vacuously true of a plan that does not exist.
        """
        build = ScenarioBuilder()
        config = PlanningConfig(
            solver_time_limit_seconds=30.0,
            solver_deterministic_budget=4.0,
            solver_optimisation_budget=4.0,
            solver_workers=1,
        )
        impossible = build.requirement("req-1", certification_codes=["DEAES"])

        solution = _solve(config, [impossible], [build.assistant()])

        assert solution.unassigned_requirement_ids == ["req-1"]
        assert solution.is_optimised is False

    @pytest.mark.parametrize("budget", [0.000001, 4.0])
    def test_the_answer_is_reproducible_whatever_the_second_budget(
        self, budget: float
    ) -> None:
        """Both the optimised and the fallback answer are stable.

        Args:
            budget (float): The optimisation budget to run at.

        Notes:
            A fallback that varied between runs would be worse than no
            fallback: a manager comparing two plans could not tell whether
            the difference was the quote they just accepted or the budget
            running out in a different place.
        """
        build = ScenarioBuilder()
        config = PlanningConfig(
            solver_time_limit_seconds=30.0,
            solver_deterministic_budget=4.0,
            solver_optimisation_budget=budget,
            solver_workers=1,
        )
        work = _round(build)
        staff = [build.assistant()]

        first = _solve(config, work, staff)
        second = _solve(config, work, staff)

        assert first.total_travel_minutes == second.total_travel_minutes
        assert first.is_optimised == second.is_optimised
