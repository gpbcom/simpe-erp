from __future__ import annotations

# Standard library imports
from datetime import date, time
import itertools
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

from models.configuration.planning_config import PlanningConfig
from models.enums import AvailabilityKind, ContractType
from models.geo.geo_point import GeoPoint
from models.people.hca import Hca
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)
from models.planning.planning_run.planning_solution import PlanningSolution
from models.settings.planning_settings import PlanningSettings

# First-party imports
from service.planning.plannings import PlanningService
from tests.annotations import ModelInput

MONDAY = date(2026, 8, 3)
TUESDAY = date(2026, 8, 4)

# Three points in central Paris, a few minutes apart at urban speed.
NEAR = GeoPoint(latitude=48.8566, longitude=2.3522)
MID = GeoPoint(latitude=48.8600, longitude=2.3600)
FAR = GeoPoint(latitude=48.8800, longitude=2.4000)


@pytest.fixture
def config() -> PlanningConfig:
    """Return a planning configuration with a short solver budget.

    Returns:
        PlanningConfig: 09:00-20:00, a one-hour lunch, two seconds to solve.
    """
    return PlanningConfig(solver_time_limit_seconds=2.0)


def _hca(
    hca_id: str = "hca-1",
    home: GeoPoint = NEAR,
    can_drive: bool = True,
    availability: Optional[List[Dict[str, ModelInput]]] = None,
) -> Hca:
    """Build an assistant whose home is already geocoded.

    Args:
        hca_id (str): The identifier to assign.
        home (GeoPoint): Where they live.
        can_drive (bool): Whether they hold a car licence.
        availability (Optional[List[Dict[str, ModelInput]]]): Absences to record.

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
            "latitude": home.latitude,
            "longitude": home.longitude,
        },
        contract_type=ContractType.CDI,
        driving_license={"categories": ["B"]} if can_drive else None,
        availability=availability or [],
    )


def _requirement(
    requirement_id: str,
    location: GeoPoint = NEAR,
    day: date = MONDAY,
    window: tuple[int, int] = (9 * 60, 20 * 60),
    duration: int = 60,
) -> InterventionRequirement:
    """Build a piece of work to be scheduled.

    Args:
        requirement_id (str): The identifier to assign.
        location (GeoPoint): Where the work happens.
        day (date): The day it must happen.
        window (tuple[int, int]): Its start and end bounds, in minutes.
        duration (int): How long it takes.

    Returns:
        InterventionRequirement: The requirement.
    """
    return InterventionRequirement(
        id=requirement_id,
        quote_line_id=f"line-{requirement_id}",
        customer_id=f"cust-{requirement_id}",
        name=f"Service {requirement_id}",
        intervention_type_id="type-1",
        day=day,
        window_start_minute=window[0],
        window_end_minute=window[1],
        duration_minutes=duration,
        location=location,
    )


def _planner(
    config: PlanningConfig,
    assistants: List[Hca],
    requirements: List[InterventionRequirement],
) -> PlanningService:
    """Return a planning service with its travel tables already built.

    Args:
        config (PlanningConfig): Supplies the two average speeds.
        assistants (List[Hca]): The workforce.
        requirements (List[InterventionRequirement]): The work.

    Returns:
        PlanningService: A service ready to solve.

    Notes:
        Built with stand-in repositories: these tests are about the constraint
        model, and nothing they exercise reads or writes.
    """
    service = PlanningService(
        runs=AsyncMock(),
        interventions=AsyncMock(),
        quotes=AsyncMock(),
        customers=AsyncMock(),
        hcas=AsyncMock(),
        types=AsyncMock(),
        settings=AsyncMock(),
        teams=AsyncMock(),
        config=config,
    )
    service.build_travel(assistants, requirements)
    return service


def _settings(
    radius_km: float = 200.0, lunch_break_minutes: int = 60
) -> PlanningSettings:
    """Return the manager-owned rules for a solve.

    Args:
        radius_km (float): The intervention radius to apply.
        lunch_break_minutes (int): The break length to reserve.

    Returns:
        PlanningSettings: The rules.

    Notes:
        The default radius is wide enough to reach every fixture point, so a
        test that is not about the radius is not silently constrained by one.
        The tests that *are* about it pass their own.
    """
    return PlanningSettings(
        max_intervention_radius_km=radius_km,
        lunch_break_minutes=lunch_break_minutes,
    )


def _solve(
    config: PlanningConfig,
    requirements: List[InterventionRequirement],
    assistants: List[Hca],
    settings: Optional[PlanningSettings] = None,
) -> PlanningSolution:
    """Run the solver over a scenario.

    Args:
        config (PlanningConfig): The planning rules.
        requirements (List[InterventionRequirement]): The work.
        assistants (List[Hca]): The workforce.
        settings (Optional[PlanningSettings]): The manager-owned rules;
            defaults to a radius wide enough not to bind.

    Returns:
        PlanningSolution: What the solver produced.
    """
    solver = PlanningService(
        runs=MagicMock(),
        interventions=MagicMock(),
        quotes=MagicMock(),
        customers=MagicMock(),
        hcas=MagicMock(),
        types=MagicMock(),
        settings=MagicMock(),
        teams=AsyncMock(),
        config=config,
    )
    solver.build_travel(assistants, requirements)
    return solver.solve(requirements, assistants, settings if settings else _settings())


class TestPlanningService:
    """Tests for the CP-SAT planning solver."""

    # ------------------------------------------------------------------ #
    #  Degenerate inputs
    # ------------------------------------------------------------------ #

    def test_no_work_is_a_valid_plan(self, config: PlanningConfig) -> None:
        """A week with nothing accepted is an answer, not an error."""
        solution = _solve(config, [], [_hca()])
        assert solution.is_feasible is True
        assert solution.assignments == []

    def test_no_assistants_leaves_everything_unassigned(
        self, config: PlanningConfig
    ) -> None:
        """Work with nobody to do it is reported, not raised."""
        solution = _solve(config, [_requirement("r1")], [])
        assert solution.is_feasible is True
        assert solution.unassigned_requirement_ids == ["r1"]

    # ------------------------------------------------------------------ #
    #  Basic scheduling
    # ------------------------------------------------------------------ #

    def test_one_assistant_one_visit(self, config: PlanningConfig) -> None:
        """The simplest plan places the visit and assigns the assistant."""
        solution = _solve(config, [_requirement("r1")], [_hca()])
        assert solution.is_complete() is True
        assert solution.assignments[0].hca_id == "hca-1"

    def test_several_visits_are_all_placed(self, config: PlanningConfig) -> None:
        """A feasible day is planned in full."""
        requirements = [
            _requirement("r1", NEAR),
            _requirement("r2", MID),
            _requirement("r3", FAR),
        ]
        solution = _solve(config, requirements, [_hca()])
        assert solution.is_complete() is True
        assert len(solution.assignments) == 3

    def test_visits_never_overlap_for_one_assistant(
        self, config: PlanningConfig
    ) -> None:
        """An assistant is never in two homes at once."""
        requirements = [
            _requirement("r1", NEAR),
            _requirement("r2", MID),
            _requirement("r3", FAR),
        ]
        solution = _solve(config, requirements, [_hca()])
        rounds = solution.assignments_by_hca()["hca-1"]
        for earlier, later in itertools.pairwise(rounds):
            assert earlier.end_minute <= later.start_minute

    # ------------------------------------------------------------------ #
    #  The working day
    # ------------------------------------------------------------------ #

    def test_nothing_is_scheduled_before_the_day_starts(
        self, config: PlanningConfig
    ) -> None:
        """The 09:00 bound holds even when the customer would allow earlier."""
        requirement = _requirement("r1", window=(0, 20 * 60))
        solution = _solve(config, [requirement], [_hca()])
        assert solution.assignments[0].start_minute >= config.day_start_minute

    def test_nothing_is_scheduled_after_the_day_ends(
        self, config: PlanningConfig
    ) -> None:
        """The 20:00 bound holds even when the customer would allow later."""
        requirement = _requirement("r1", window=(0, 24 * 60))
        solution = _solve(config, [requirement], [_hca()])
        assert solution.assignments[0].end_minute <= config.day_end_minute

    def test_the_customer_window_is_respected(self, config: PlanningConfig) -> None:
        """A morning-only visit is not moved to the afternoon."""
        requirement = _requirement("r1", window=(9 * 60, 11 * 60), duration=60)
        solution = _solve(config, [requirement], [_hca()])
        assignment = solution.assignments[0]
        assert assignment.start_minute >= 9 * 60
        assert assignment.end_minute <= 11 * 60

    # ------------------------------------------------------------------ #
    #  The lunch break
    # ------------------------------------------------------------------ #

    def test_an_uninterrupted_lunch_break_is_left(self, config: PlanningConfig) -> None:
        """A full day still leaves at least one hour free over midday.

        Notes:
            The break is modelled as an interval competing for the same
            no-overlap resource, so nothing can be scheduled across it.
        """
        requirements = [
            _requirement(f"r{index}", NEAR, duration=60) for index in range(6)
        ]
        solution = _solve(config, requirements, [_hca()])
        assert solution.is_complete() is True
        rounds = solution.assignments_by_hca()["hca-1"]
        gaps = [
            later.start_minute - earlier.end_minute
            for earlier, later in itertools.pairwise(rounds)
        ]
        midday_gap = max(gaps) if gaps else 0
        assert midday_gap >= _settings().lunch_break_minutes

    def test_a_longer_configured_break_is_honoured(self) -> None:
        """The break duration is configurable, as the business requires.

        Notes:
            The length now comes from the stored settings a manager owns, not
            from the configuration file, so this passes it in that way — which
            is also the path an administrator's change takes.
        """
        config = PlanningConfig(
            lunch_window_start_minute=11 * 60,
            lunch_window_end_minute=15 * 60,
            solver_time_limit_seconds=2.0,
        )
        requirements = [
            _requirement(f"r{index}", NEAR, duration=60) for index in range(5)
        ]
        solution = _solve(
            config, requirements, [_hca()], _settings(lunch_break_minutes=90)
        )
        assert solution.is_complete() is True
        rounds = solution.assignments_by_hca()["hca-1"]
        gaps = [
            later.start_minute - earlier.end_minute
            for earlier, later in itertools.pairwise(rounds)
        ]
        assert max(gaps) >= 90

    # ------------------------------------------------------------------ #
    #  Availability
    # ------------------------------------------------------------------ #

    def test_an_absent_assistant_gets_no_work(self, config: PlanningConfig) -> None:
        """A whole-day absence removes the assistant from that day."""
        away = _hca(
            availability=[
                {
                    "hca_id": "hca-1",
                    "start_date": MONDAY,
                    "end_date": MONDAY,
                    "kind": AvailabilityKind.HOLIDAY,
                }
            ]
        )
        solution = _solve(config, [_requirement("r1", day=MONDAY)], [away])
        assert solution.unassigned_requirement_ids == ["r1"]

    def test_an_absence_only_blocks_its_own_day(self, config: PlanningConfig) -> None:
        """Monday off does not stop Tuesday's work."""
        away = _hca(
            availability=[
                {
                    "hca_id": "hca-1",
                    "start_date": MONDAY,
                    "end_date": MONDAY,
                    "kind": AvailabilityKind.HOLIDAY,
                }
            ]
        )
        solution = _solve(config, [_requirement("r1", day=TUESDAY)], [away])
        assert solution.is_complete() is True

    def test_a_partial_absence_leaves_the_rest_of_the_day(
        self, config: PlanningConfig
    ) -> None:
        """A morning of training blocks the morning, not the day.

        Notes:
            The absence joins the same no-overlap constraint as the visits, so
            the afternoon stays schedulable.
        """
        training = _hca(
            availability=[
                {
                    "hca_id": "hca-1",
                    "start_date": MONDAY,
                    "end_date": MONDAY,
                    "kind": AvailabilityKind.TRAINING,
                    "start_time": time(9, 0),
                    "end_time": time(12, 0),
                }
            ]
        )
        solution = _solve(config, [_requirement("r1", day=MONDAY)], [training])
        assert solution.is_complete() is True
        assert solution.assignments[0].start_minute >= 12 * 60

    def test_an_assistant_with_no_home_coordinate_gets_no_work(
        self, config: PlanningConfig
    ) -> None:
        """An unroutable assistant is left free rather than planned blindly."""
        unroutable = Hca(
            company_id="company-1",
            id="hca-lost",
            first_name="Sans",
            last_name="Adresse",
            phone_number="+33612345678",
            email="lost@example.com",
            address={
                "street": "1 rue Inconnue",
                "postal_code": "99999",
                "city": "Nulle Part",
                "geocoding_error": "not_found",
            },
            contract_type=ContractType.CDI,
        )
        solution = _solve(config, [_requirement("r1")], [unroutable])
        assert solution.unassigned_requirement_ids == ["r1"]

    # ------------------------------------------------------------------ #
    #  Impossible work is reported, never fatal
    # ------------------------------------------------------------------ #

    def test_work_that_cannot_fit_is_reported_not_raised(
        self, config: PlanningConfig
    ) -> None:
        """Too much work for one day leaves the excess listed.

        Notes:
            This is the property that makes the planner usable: a manager can
            act on "here is the week, minus these", but not on "infeasible".
        """
        requirements = [
            _requirement(f"r{index}", NEAR, window=(9 * 60, 11 * 60), duration=60)
            for index in range(5)
        ]
        solution = _solve(config, requirements, [_hca()])
        assert solution.is_feasible is True
        assert solution.assignments
        assert solution.unassigned_requirement_ids

    def test_dropping_work_is_a_last_resort(self, config: PlanningConfig) -> None:
        """A distant visit is driven to rather than dropped.

        Notes:
            The unassigned penalty dominates travel precisely so the solver
            cannot discover that skipping a far customer is 'cheaper'.
        """
        solution = _solve(config, [_requirement("r1", FAR)], [_hca(home=NEAR)])
        assert solution.is_complete() is True

    # ------------------------------------------------------------------ #
    #  Travel
    # ------------------------------------------------------------------ #

    def test_travel_time_is_left_between_visits(self, config: PlanningConfig) -> None:
        """Consecutive visits are separated by at least the journey."""
        requirements = [_requirement("r1", NEAR), _requirement("r2", FAR)]
        solution = _solve(config, requirements, [_hca()])
        rounds = solution.assignments_by_hca()["hca-1"]
        planner = _planner(config, [_hca()], requirements)
        by_id = {item.id: item for item in requirements}
        for earlier, later in itertools.pairwise(rounds):
            travel = planner.travel_between_points(
                "hca-1",
                by_id[earlier.requirement_id].location,
                by_id[later.requirement_id].location,
            )
            assert later.start_minute - earlier.end_minute >= travel

    def test_the_reported_travel_is_non_zero_when_moving(
        self, config: PlanningConfig
    ) -> None:
        """A round that goes somewhere costs travel."""
        solution = _solve(config, [_requirement("r1", FAR)], [_hca(home=NEAR)])
        assert solution.total_travel_minutes > 0

    def test_the_nearer_assistant_is_preferred(self, config: PlanningConfig) -> None:
        """Minimising travel means the closer assistant takes the work."""
        near_assistant = _hca("hca-near", home=NEAR)
        far_assistant = _hca("hca-far", home=FAR)
        solution = _solve(
            config, [_requirement("r1", NEAR)], [near_assistant, far_assistant]
        )
        assert solution.is_complete() is True
        assert solution.assignments[0].hca_id == "hca-near"

    def test_a_licence_less_assistant_travels_more_slowly(
        self, config: PlanningConfig
    ) -> None:
        """The driving licence changes which travel resolver applies.

        Notes:
            Assuming car speed for somebody on public transport would produce a
            round they cannot keep.
        """
        driver = _hca("hca-driver", home=NEAR, can_drive=True)
        walker = _hca("hca-walker", home=NEAR, can_drive=False)
        requirements = [_requirement("r1", FAR)]
        planner = _planner(config, [driver, walker], requirements)
        driver_leg = planner.travel_between_points("hca-driver", NEAR, FAR)
        walker_leg = planner.travel_between_points("hca-walker", NEAR, FAR)
        assert walker_leg > driver_leg

    # ------------------------------------------------------------------ #
    #  Multiple assistants and days
    # ------------------------------------------------------------------ #

    def test_work_is_shared_when_one_assistant_cannot_take_it_all(
        self, config: PlanningConfig
    ) -> None:
        """A day too full for one person is split across two."""
        requirements = [
            _requirement(f"r{index}", NEAR, window=(9 * 60, 12 * 60), duration=60)
            for index in range(4)
        ]
        solution = _solve(config, requirements, [_hca("hca-1"), _hca("hca-2")])
        assert len(solution.assignments_by_hca()) == 2

    def test_each_requirement_is_assigned_exactly_once(
        self, config: PlanningConfig
    ) -> None:
        """No visit is duplicated across assistants."""
        requirements = [_requirement(f"r{index}", NEAR) for index in range(3)]
        solution = _solve(config, requirements, [_hca("hca-1"), _hca("hca-2")])
        placed = [entry.requirement_id for entry in solution.assignments]
        assert len(placed) == len(set(placed))
        assert set(placed) | set(solution.unassigned_requirement_ids) == {
            "r0",
            "r1",
            "r2",
        }

    def test_two_days_are_planned_independently(self, config: PlanningConfig) -> None:
        """Monday's round does not constrain Tuesday's."""
        requirements = [
            _requirement("r1", NEAR, day=MONDAY),
            _requirement("r2", NEAR, day=TUESDAY),
        ]
        solution = _solve(config, requirements, [_hca()])
        assert solution.is_complete() is True
        assert len(solution.assignments) == 2

    def test_the_solver_is_reusable(self, config: PlanningConfig) -> None:
        """A second solve does not inherit the first one's variables."""
        solver = PlanningService(
            runs=MagicMock(),
            interventions=MagicMock(),
            quotes=MagicMock(),
            customers=MagicMock(),
            hcas=MagicMock(),
            types=MagicMock(),
            settings=MagicMock(),
            teams=AsyncMock(),
            config=config,
        )
        assistants = [_hca()]
        first = [_requirement("r1")]
        second = [_requirement("r2"), _requirement("r3")]
        solver.build_travel(assistants, first + second)
        solver.solve(first, assistants, _settings())
        solution = solver.solve(second, assistants, _settings())
        assert len(solution.assignments) == 2
        assert {entry.requirement_id for entry in solution.assignments} == {
            "r2",
            "r3",
        }
