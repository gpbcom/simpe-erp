from __future__ import annotations

# Standard library imports
from datetime import date
from typing import List
from unittest.mock import MagicMock

# Third-party imports
import pytest

# First-party imports
from models.configuration.planning_config import PlanningConfig
from models.enums import ContractType, UnplacedReason
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
        # One quote for every visit in these fixtures, so a report grouped by
        # quote has something real to group by.
        quote_reference="DEV-2026-0001",
        customer_name="Marie Durand",
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
    """Run the report over an empty solve and return the message it raises.

    Args:
        solution (PlanningSolution): What the solver returned.
        requirements: The submitted work.

    Returns:
        str: The failure message.

    Notes:
        Only an **empty** solve raises now. A solve that placed some of the
        week returns a report instead and the plan is stored, so a partial
        result goes through :func:`_report` below.
    """
    with pytest.raises(MTPlanningInfeasible) as raised:
        _service()._report_unplaced(
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
            _service()._report_unplaced(
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


class TestAPartialPlanIsKeptAndReported:
    """Tests for a week that mostly worked.

    Notes:
        **This is where the rule changed.** A run used to fail outright the
        moment one visit could not be placed: the whole week was withheld, the
        agency kept the previous calendar, and the operator got one long
        sentence quoting a solver status and a configuration key. Safe, and
        unusable — one impossible visit took eighty-nine good ones with it.

        The plan is now stored and the gap is reported. What must not happen
        is the gap becoming invisible, so these tests pin the report itself:
        every unplaced visit is accounted for, grouped under the quote it was
        sold on, with the customer named and a reason attached.

        An empty solve is still refused, and the class above still proves it.
        Nothing is stored in that case because nothing was found.
    """

    def _report(
        self, solution: PlanningSolution, requirements, radius_km: float = 200.0
    ):
        """Run the report and return the quotes it names.

        Args:
            solution (PlanningSolution): What the solver returned.
            requirements: The submitted work.
            radius_km (float): The intervention radius to diagnose under.

        Returns:
            List[UnplacedQuote]: One entry per quote with unplaced work.
        """
        return _service()._report_unplaced(
            solution,
            requirements,
            [_hca()],
            PlanningSettings(max_intervention_radius_km=radius_km),
        )

    def test_a_partial_plan_is_no_longer_refused(self) -> None:
        """The run continues, where it used to raise.

        Notes:
            The single most important assertion in this file. If this starts
            raising again, an agency loses a working week over one visit.
        """
        requirements = [_requirement("req-1"), _requirement("req-2")]

        report = self._report(_partial("FEASIBLE"), requirements)

        assert report != []

    def test_the_report_names_the_quote_that_could_not_be_fitted(self) -> None:
        """A visit identifier is not something anybody can act on."""
        requirements = [_requirement("req-1"), _requirement("req-2")]

        report = self._report(_partial("FEASIBLE"), requirements)

        assert [entry.quote_reference for entry in report] == ["DEV-2026-0001"]

    def test_the_report_covers_every_unplaced_visit_and_no_others(self) -> None:
        """Both directions: nothing invented, and nothing quietly dropped."""
        requirements = [_requirement("req-1"), _requirement("req-2")]

        report = self._report(_partial("FEASIBLE"), requirements)

        placed = [visit.requirement_id for entry in report for visit in entry.visits]
        assert placed == ["req-2"]

    def test_each_unplaced_visit_carries_a_reason(self) -> None:
        """"It did not fit" is not an answer anybody can act on."""
        requirements = [_requirement("req-1"), _requirement("req-2")]

        report = self._report(_partial("FEASIBLE"), requirements, radius_km=0.1)

        reasons = [visit.reason.value for entry in report for visit in entry.visits]
        assert reasons == ["out-of-radius"]

    def test_several_visits_of_one_quote_are_one_finding(self) -> None:
        """Three visits blocked by one cause are one problem, not three.

        Notes:
            Repeating the same sentence per visit is what made the old message
            unreadable at ninety visits.
        """
        requirements = [_requirement(f"req-{index}") for index in range(4)]
        solution = PlanningSolution(
            assignments=[],
            unassigned_requirement_ids=["req-1", "req-2", "req-3"],
            total_travel_minutes=10,
            is_feasible=True,
            status_name="FEASIBLE",
        )

        report = self._report(solution, requirements, radius_km=0.1)

        assert len(report) == 1
        assert len(report[0].visits) == 3
        assert report[0].reasons() == [UnplacedReason.OUT_OF_RADIUS]

    def test_a_complete_plan_reports_nothing(self) -> None:
        """Silence is the right answer when the whole week fitted."""
        requirements = [_requirement("req-1")]
        solution = PlanningSolution(
            assignments=[],
            unassigned_requirement_ids=[],
            total_travel_minutes=10,
            is_feasible=True,
            status_name="OPTIMAL",
        )

        assert self._report(solution, requirements) == []
