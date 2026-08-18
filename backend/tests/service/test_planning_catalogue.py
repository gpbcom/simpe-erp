from __future__ import annotations

# Third-party imports
import pytest

# First-party imports
from models.configuration.planning_config import PlanningConfig
from models.planning.planning_run.planning_solution import PlanningSolution

# Local imports
from tests.planning_scenarios.catalogue import ScenarioCatalogue
from tests.planning_scenarios.scenario import PlanningScenario

CATALOGUE = ScenarioCatalogue().all()


@pytest.fixture
def config() -> PlanningConfig:
    """Return a planning configuration with a short solver budget.

    Returns:
        PlanningConfig: Enough budget for instances of a handful of visits.
    """
    return PlanningConfig(
        solver_time_limit_seconds=20.0,
        solver_deterministic_budget=4.0,
        solver_workers=1,
    )


def _solve(config: PlanningConfig, scenario: PlanningScenario) -> PlanningSolution:
    """Run one scenario through the solver.

    Args:
        config (PlanningConfig): The planning rules.
        scenario (PlanningScenario): The instance to solve.

    Returns:
        PlanningSolution: What the solver produced.

    Notes:
        Goes through the public ``build_travel`` + ``solve`` pair rather than
        any internal, so the harness keeps working across a refactor of how
        the model is built. That is the entire point of it.
    """
    service = ScenarioCatalogue().build.service(config)
    service.build_travel(scenario.assistants, scenario.requirements)
    return service.solve(scenario.requirements, scenario.assistants, scenario.settings)


class TestTheScenarioCatalogue:
    """Runs every catalogue case against the solver.

    Notes:
        **This file is the contract for the per-day refactor.** It must pass
        unmodified before and after, because it asserts on nothing but the
        public entry points and the outcome. A case that needs editing to go
        green is a behaviour change that has to be justified rather than a
        test that needs fixing.
    """

    @pytest.mark.parametrize("scenario", CATALOGUE, ids=lambda case: case.name)
    def test_the_solver_finds_a_plan_when_one_exists(
        self, config: PlanningConfig, scenario: PlanningScenario
    ) -> None:
        """Feasibility is reported as the case says it should be.

        Args:
            config (PlanningConfig): The planning rules.
            scenario (PlanningScenario): The case under test.
        """
        solution = _solve(config, scenario)

        assert solution.is_feasible is scenario.expect_feasible

    @pytest.mark.parametrize("scenario", CATALOGUE, ids=lambda case: case.name)
    def test_exactly_the_expected_work_goes_unplaced(
        self, config: PlanningConfig, scenario: PlanningScenario
    ) -> None:
        """Both directions matter: nothing extra, and nothing missing.

        Args:
            config (PlanningConfig): The planning rules.
            scenario (PlanningScenario): The case under test.

        Notes:
            Skipped for the infeasible cases, where the solver returns every
            requirement as unplaced by convention rather than as a finding
            about any of them.
        """
        if not scenario.expect_feasible:
            pytest.skip("An infeasible solve reports everything, which means nothing.")

        solution = _solve(config, scenario)

        assert sorted(solution.unassigned_requirement_ids) == sorted(
            scenario.expect_unplaced_ids
        )

    @pytest.mark.parametrize(
        "scenario",
        [case for case in CATALOGUE if case.expect_assignee],
        ids=lambda case: case.name,
    )
    def test_the_right_assistant_is_chosen(
        self, config: PlanningConfig, scenario: PlanningScenario
    ) -> None:
        """A qualification gate selects as well as excludes.

        Args:
            config (PlanningConfig): The planning rules.
            scenario (PlanningScenario): The case under test.
        """
        solution = _solve(config, scenario)

        assert solution.assignments[0].hca_id == scenario.expect_assignee

    @pytest.mark.parametrize(
        "scenario",
        [case for case in CATALOGUE if case.expect_reason],
        ids=lambda case: case.name,
    )
    def test_the_diagnosis_names_the_obstacle(
        self, config: PlanningConfig, scenario: PlanningScenario
    ) -> None:
        """The reason a manager is shown is the one they can act on.

        Args:
            config (PlanningConfig): The planning rules.
            scenario (PlanningScenario): The case under test.

        Notes:
            Asserted separately from the unplaced set because the two fail
            for different reasons: the set is the solver's decision, the
            reason is the diagnosis ladder's reading of it, and a refactor
            can break one without the other.
        """
        service = ScenarioCatalogue().build.service(config)
        service.build_travel(scenario.assistants, scenario.requirements)
        solution = service.solve(
            scenario.requirements, scenario.assistants, scenario.settings
        )

        explained = service.explain_unplaced(
            solution.unassigned_requirement_ids,
            scenario.requirements,
            scenario.assistants,
            scenario.settings,
        )

        assert [item.reason for item in explained] == [scenario.expect_reason]

    @pytest.mark.parametrize("scenario", CATALOGUE, ids=lambda case: case.name)
    def test_the_same_instance_plans_identically_twice(
        self, config: PlanningConfig, scenario: PlanningScenario
    ) -> None:
        """Re-planning an unchanged week must not move the answer.

        Args:
            config (PlanningConfig): The planning rules.
            scenario (PlanningScenario): The case under test.

        Notes:
            The original complaint that started this work: one week replanned
            three times returned 404, then 371, then 355 minutes of travel,
            and a manager had no way to tell an improvement from noise. At one
            search worker this holds. The assertion is here so that the
            per-day refactor cannot quietly give it up again.
        """
        first = _solve(config, scenario)
        second = _solve(config, scenario)

        assert first.total_travel_minutes == second.total_travel_minutes
        assert [
            (item.requirement_id, item.hca_id, item.start_minute)
            for item in first.assignments
        ] == [
            (item.requirement_id, item.hca_id, item.start_minute)
            for item in second.assignments
        ]
