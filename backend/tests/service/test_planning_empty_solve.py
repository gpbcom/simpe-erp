from __future__ import annotations

# Standard library imports
from datetime import date
from typing import List
from unittest.mock import MagicMock

# Third-party imports
import pytest

# First-party imports
from models.configuration.planning_config import PlanningConfig
from models.enums import ContractType
from models.geo.geo_point import GeoPoint
from models.people.hca import Hca
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)
from models.planning.planning_run.planning_solution import PlanningSolution
from models.settings.planning_settings import PlanningSettings
from service.planning.exceptions import MTPlanningInfeasible
from service.planning.plannings import PlanningService

MONDAY = date(2026, 8, 3)
HOME = GeoPoint(latitude=48.8566, longitude=2.3522)
NEARBY = GeoPoint(latitude=48.8600, longitude=2.3550)


def _hca(hca_id: str = "hca-1") -> Hca:
    """Build an assistant whose home is geocoded and near the work.

    Args:
        hca_id (str): The identifier to assign.

    Returns:
        Hca: The assistant.
    """
    return Hca(
        company_id="company-1",
        id=hca_id,
        first_name="Luc",
        last_name=hca_id.upper(),
        phone_number="+33612345678",
        email=f"{hca_id}@example.com",
        address={
            "street": "1 rue A",
            "postal_code": "75001",
            "city": "Paris",
            "latitude": HOME.latitude,
            "longitude": HOME.longitude,
        },
        contract_type=ContractType.CDI,
        driving_license={"categories": ["B"]},
    )


def _requirement(requirement_id: str) -> InterventionRequirement:
    """Build one ungated, reachable piece of work.

    Args:
        requirement_id (str): The identifier to assign.

    Returns:
        InterventionRequirement: The work.
    """
    return InterventionRequirement(
        id=requirement_id,
        quote_line_id=requirement_id,
        customer_id=f"customer-{requirement_id}",
        name="Aide a la toilette",
        intervention_type_id="type-1",
        day=MONDAY,
        window_start_minute=9 * 60,
        window_end_minute=20 * 60,
        duration_minutes=60,
        location=NEARBY,
    )


def _service() -> PlanningService:
    """Return a planning service over stand-in repositories.

    Returns:
        PlanningService: The service under test.
    """
    return PlanningService(
        runs=MagicMock(),
        interventions=MagicMock(),
        quotes=MagicMock(),
        customers=MagicMock(),
        hcas=MagicMock(),
        types=MagicMock(),
        settings=MagicMock(),
        config=PlanningConfig(),
    )


def _empty(status_name: str, requirements: List[InterventionRequirement]) -> PlanningSolution:
    """Build the solution a solve that produced nothing returns.

    Args:
        status_name (str): The solver status.
        requirements (List[InterventionRequirement]): The submitted work.

    Returns:
        PlanningSolution: Every requirement unassigned, not feasible.
    """
    return PlanningSolution(
        assignments=[],
        unassigned_requirement_ids=[item.id for item in requirements],
        total_travel_minutes=0,
        is_feasible=False,
        status_name=status_name,
    )


def _refuse(solution: PlanningSolution, requirements) -> str:
    """Run the refusal and return the message it raises.

    Args:
        solution (PlanningSolution): What the solver returned.
        requirements: The submitted work.

    Returns:
        str: The failure message.
    """
    with pytest.raises(MTPlanningInfeasible) as raised:
        _service()._require_complete(
            solution,
            requirements,
            [_hca()],
            PlanningSettings(max_intervention_radius_km=200.0),
        )
    return str(raised.value)


class TestASolveThatProducedNothing:
    """Tests for what the run says when the solver returned no plan at all.

    Notes:
        **This is what a run reported as "77 of 77 visits could not be
        scheduled — travel, the lunch break and the other visits that day
        leave no room for it", seventy-seven times.** None of that was
        established. The solver had stopped without a solution, every
        requirement came back unassigned, and ``explain_unplaced`` re-checked
        what it could decide alone — the radius, the qualifications, the
        working day — then fell through to the catch-all for all of them.

        The catch-all reads as a finding about that visit. It is not, and the
        difference matters: it sent the reader to move windows and widen radii
        for a problem whose answer was a bigger budget.
    """

    def test_an_exhausted_search_does_not_blame_travel_and_lunch(self) -> None:
        """``UNKNOWN`` proves nothing, and the message must not pretend it did."""
        requirements = [_requirement(f"req-{index}") for index in range(3)]

        message = _refuse(_empty("UNKNOWN", requirements), requirements)

        assert "lunch" not in message
        assert "leave no room" not in message

    def test_an_exhausted_search_names_the_lever(self) -> None:
        """The reader needs the one thing that would change the outcome."""
        requirements = [_requirement("req-1")]

        message = _refuse(_empty("UNKNOWN", requirements), requirements)

        assert "solver_deterministic_budget" in message
        assert "UNKNOWN" in message

    def test_an_exhausted_search_says_nothing_was_proved(self) -> None:
        """"No plan found" and "no plan exists" are different answers."""
        requirements = [_requirement("req-1")]

        message = _refuse(_empty("UNKNOWN", requirements), requirements)

        assert "not a proof" in message

    def test_a_proof_of_infeasibility_says_it_is_one(self) -> None:
        """``INFEASIBLE`` is the one status that really did settle it."""
        requirements = [_requirement("req-1")]

        message = _refuse(_empty("INFEASIBLE", requirements), requirements)

        assert "proved it" in message
        assert "budget" not in message

    def test_the_message_does_not_repeat_itself_once_per_visit(self) -> None:
        """Seventy-seven identical sentences are not seventy-seven findings."""
        requirements = [_requirement(f"req-{index}") for index in range(77)]

        message = _refuse(_empty("UNKNOWN", requirements), requirements)

        assert message.count("Aide a la toilette") == 0
        assert len(message) < 400

    def test_a_specific_obstacle_is_still_named(self) -> None:
        """A visit nobody can reach is a fact whatever the solver then did.

        Notes:
            These are the reasons ``explain_unplaced`` establishes on its own,
            and they are often *why* the solve got nowhere — so they survive
            into the message while the catch-all does not.
        """
        requirements = [_requirement("req-1")]

        with pytest.raises(MTPlanningInfeasible) as raised:
            _service()._require_complete(
                _empty("UNKNOWN", requirements),
                requirements,
                [_hca()],
                # The narrowest radius the settings accept: the work sits
                # ~400 m from the assistant's home, so 0.1 km puts it out of
                # reach and the diagnosis has something real to report.
                PlanningSettings(max_intervention_radius_km=0.1),
            )

        assert "out-of-radius" in str(raised.value)


def _partial(status_name: str) -> PlanningSolution:
    """Build a plan that placed one visit of two.

    Args:
        status_name (str): The solver status.

    Returns:
        PlanningSolution: A feasible solution missing ``req-2``.
    """
    return PlanningSolution(
        assignments=[],
        unassigned_requirement_ids=["req-2"],
        total_travel_minutes=10,
        is_feasible=True,
        status_name=status_name,
    )


class TestAPartialPlanTheSolverProvedBest:
    """Tests the per-visit diagnosis where the solver really did settle it."""

    def test_an_optimal_solve_missing_one_visit_names_it(self) -> None:
        """**The case the per-visit reasons were written for.**

        Notes:
            ``OPTIMAL`` means the search finished: it looked everywhere and
            this was the best plan there is. An unplaced visit costs
            ``unassigned_penalty``, so one left out of an optimal plan really
            could not be fitted — "travel, lunch and the other visits leave no
            room" is a finding rather than a guess.
        """
        requirements = [_requirement("req-1"), _requirement("req-2")]

        message = _refuse(_partial("OPTIMAL"), requirements)

        assert "1 of 2 visit(s) could not be scheduled" in message
        assert "Aide a la toilette" in message


class TestAPartialPlanTheSolverNeverProvedBest:
    """Tests for a plan that merely happens to be the best one *found*.

    Notes:
        **This is what a run reported as "2 of 77 visits could not be
        scheduled — travel, the lunch break and the other visits that day
        leave no room for it".** The status was ``FEASIBLE``: the solver had
        found a plan and stopped on its deterministic budget without proving
        it was the best one.

        An unplaced visit is the most expensive term in the objective — a
        hundred thousand against a travel minute's one — so a search that could
        have placed those two would have. Leaving them out is evidence the
        search ran out of budget, not that the day is full. Saying otherwise
        sends a manager to move a customer's hours to solve an arithmetic
        problem.
    """

    def test_a_feasible_solve_does_not_blame_travel_and_lunch(self) -> None:
        """Nothing about those visits was established."""
        requirements = [_requirement("req-1"), _requirement("req-2")]

        message = _refuse(_partial("FEASIBLE"), requirements)

        assert "lunch" not in message
        assert "leave no room" not in message

    def test_a_feasible_solve_still_reports_the_size_of_the_gap(self) -> None:
        """How much did not fit is a fact, and the number people act on."""
        requirements = [_requirement("req-1"), _requirement("req-2")]

        message = _refuse(_partial("FEASIBLE"), requirements)

        assert "1 of 2 visit(s) unscheduled" in message
        assert "FEASIBLE" in message

    def test_a_feasible_solve_names_the_lever_before_the_rota(self) -> None:
        """The budget is the thing to try first, and the message says so."""
        requirements = [_requirement("req-1"), _requirement("req-2")]

        message = _refuse(_partial("FEASIBLE"), requirements)

        assert "solver_deterministic_budget" in message
        assert "before moving anybody's hours" in message

    def test_a_feasible_solve_says_nothing_was_proved(self) -> None:
        """"Not placed" and "cannot be placed" are different claims."""
        requirements = [_requirement("req-1"), _requirement("req-2")]

        message = _refuse(_partial("FEASIBLE"), requirements)

        assert "not a proof" in message

    def test_a_specific_obstacle_survives_into_the_message(self) -> None:
        """A visit nobody can reach is a fact whatever the search then did."""
        requirements = [_requirement("req-1"), _requirement("req-2")]

        with pytest.raises(MTPlanningInfeasible) as raised:
            _service()._require_complete(
                _partial("FEASIBLE"),
                requirements,
                [_hca()],
                PlanningSettings(max_intervention_radius_km=0.1),
            )

        assert "out-of-radius" in str(raised.value)
