from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.configuration.planning_config import PlanningConfig
from models.enums import AvailabilityKind, ContractType, UnplacedReason
from models.geo.geo_point import GeoPoint
from models.people.hca import Hca
from models.planning.exceptions import MTRequirementInvalidWindow
from models.planning.intervention_requirement import InterventionRequirement
from models.settings.planning_settings import PlanningSettings
from service.planning.plannings import PlanningService

MONDAY = date(2026, 8, 3)

# Central Paris, then a point roughly 9 km east, then Reims — about 130 km away.
HOME = GeoPoint(latitude=48.8566, longitude=2.3522)
NEARBY = GeoPoint(latitude=48.8566, longitude=2.4750)
FAR_AWAY = GeoPoint(latitude=49.2583, longitude=4.0317)


@pytest.fixture
def config() -> PlanningConfig:
    """Return a planning configuration with a short solver budget.

    Returns:
        PlanningConfig: 09:00-20:00, two seconds to solve.
    """
    return PlanningConfig(solver_time_limit_seconds=2.0)


def _hca(
    hca_id: str = "hca-1",
    home: GeoPoint = HOME,
    availability: Optional[List[Dict[str, object]]] = None,
) -> Hca:
    """Build an assistant whose home is already geocoded.

    Args:
        hca_id (str): The identifier to assign.
        home (GeoPoint): Where they live.
        availability (Optional[List[Dict[str, object]]]): Absences to record.

    Returns:
        Hca: The assistant.
    """
    return Hca(
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
        driving_license={"categories": ["B"]},
        availability=availability or [],
    )


def _requirement(
    requirement_id: str,
    location: GeoPoint = NEARBY,
    customer_id: Optional[str] = None,
    window: tuple[int, int] = (9 * 60, 20 * 60),
    duration: int = 60,
    day: date = MONDAY,
) -> InterventionRequirement:
    """Build a piece of work to be scheduled.

    Args:
        requirement_id (str): The identifier to assign.
        location (GeoPoint): Where the work happens.
        customer_id (Optional[str]): Whose work it is; defaults to its own.
        window (tuple[int, int]): Its start and end bounds, in minutes.
        duration (int): How long it takes.
        day (date): The day it must happen.

    Returns:
        InterventionRequirement: The requirement.
    """
    return InterventionRequirement(
        id=requirement_id,
        quote_line_id=f"line-{requirement_id}",
        customer_id=customer_id if customer_id else f"cust-{requirement_id}",
        name=f"Service {requirement_id}",
        intervention_type_id="type-1",
        day=day,
        window_start_minute=window[0],
        window_end_minute=window[1],
        duration_minutes=duration,
        location=location,
    )


def _solve(
    config: PlanningConfig,
    requirements: List[InterventionRequirement],
    assistants: List[Hca],
    radius_km: float = 200.0,
):
    """Run the solver over a scenario with a given radius.

    Args:
        config (PlanningConfig): The planning rules.
        requirements (List[InterventionRequirement]): The work.
        assistants (List[Hca]): The workforce.
        radius_km (float): The intervention radius to apply.

    Returns:
        PlanningSolution: What the solver produced.
    """
    service = PlanningService(
        runs=MagicMock(),
        interventions=MagicMock(),
        quotes=MagicMock(),
        customers=MagicMock(),
        hcas=MagicMock(),
        settings=MagicMock(),
        config=config,
    )
    # The travel tables live on the service now, keyed by assistant, and every
    # solve builds its own first.
    service.build_travel(assistants, requirements)
    return service.solve(
        requirements,
        assistants,
        PlanningSettings(max_intervention_radius_km=radius_km),
    )


class TestInterventionRadius:
    """Tests for the radius an administrator or manager configures."""

    # ------------------------------------------------------------------ #
    #  The constraint binds
    # ------------------------------------------------------------------ #

    def test_work_inside_the_radius_is_placed(self, config: PlanningConfig) -> None:
        """A visit within reach is scheduled as usual."""
        solution = _solve(config, [_requirement("r1", NEARBY)], [_hca()], radius_km=20)

        assert solution.is_complete() is True

    def test_work_beyond_the_radius_is_never_assigned(
        self, config: PlanningConfig
    ) -> None:
        """An assistant is not sent past the limit, however free their day.

        Notes:
            The assistant here has an empty diary and the visit has an
            eleven-hour window — everything except the distance says yes. That
            is the point: the radius is a limit, not a preference the solver
            may outweigh when the alternative is leaving work unplaced.
        """
        solution = _solve(
            config, [_requirement("r1", FAR_AWAY)], [_hca()], radius_km=20
        )

        assert solution.assignments == []
        assert solution.unassigned_requirement_ids == ["r1"]

    def test_the_radius_is_measured_from_home_not_between_visits(
        self, config: PlanningConfig
    ) -> None:
        """A chain of short hops still cannot end beyond the radius.

        Notes:
            This is the distinction the rule turns on. Measuring only between
            consecutive visits would let an assistant walk out of their area
            one neighbourhood at a time and finish the day 130 km from home.
        """
        requirements = [
            _requirement("near", NEARBY),
            _requirement("far", FAR_AWAY),
        ]
        solution = _solve(config, requirements, [_hca()], radius_km=20)

        placed = {entry.requirement_id for entry in solution.assignments}
        assert placed == {"near"}
        assert solution.unassigned_requirement_ids == ["far"]

    def test_a_wider_radius_reaches_further(self, config: PlanningConfig) -> None:
        """The same work becomes placeable when a manager widens the radius.

        Notes:
            The pair of assertions is what proves the radius is what decided
            it: nothing about the scenario changes except the configured
            number.
        """
        requirements = [_requirement("r1", FAR_AWAY)]

        assert _solve(config, requirements, [_hca()], radius_km=20).assignments == []
        assert _solve(config, requirements, [_hca()], radius_km=200).is_complete()

    def test_a_boundary_visit_is_inside_the_radius(
        self, config: PlanningConfig
    ) -> None:
        """A visit exactly at the limit is within it.

        Notes:
            Inclusive at the boundary, so a round-numbered radius behaves like
            the number an administrator typed rather than one metre tighter.
        """
        distance = HOME.distance_km(NEARBY)
        solution = _solve(
            config, [_requirement("r1", NEARBY)], [_hca()], radius_km=distance
        )

        assert solution.is_complete() is True

    def test_a_nearer_assistant_takes_work_the_far_one_cannot(
        self, config: PlanningConfig
    ) -> None:
        """The radius narrows who may take a visit, not whether it happens."""
        near_assistant = _hca("near-one", home=HOME)
        far_assistant = _hca("far-one", home=FAR_AWAY)
        solution = _solve(
            config, [_requirement("r1", NEARBY)], [near_assistant, far_assistant], 20
        )

        assert solution.assignments[0].hca_id == "near-one"

    def test_an_assistant_with_no_resolved_home_is_given_nothing(
        self, config: PlanningConfig
    ) -> None:
        """An unlocatable assistant cannot be checked against the radius.

        Notes:
            Assuming they are inside it would route somebody from a place
            nobody can find, and every distance in their round would be
            fiction.
        """
        homeless = _hca()
        homeless.address.latitude = None
        homeless.address.longitude = None

        solution = _solve(config, [_requirement("r1", NEARBY)], [homeless], 200)

        assert solution.assignments == []


class TestCustomerConflicts:
    """Tests for the rule that a customer is never visited twice at once."""

    def test_two_visits_to_one_customer_do_not_overlap(
        self, config: PlanningConfig
    ) -> None:
        """Both are placed, one after the other."""
        requirements = [
            _requirement("r1", customer_id="cust-1", duration=60),
            _requirement("r2", customer_id="cust-1", duration=60),
        ]
        solution = _solve(config, requirements, [_hca()])

        assert solution.is_complete() is True
        placed = sorted(solution.assignments, key=lambda entry: entry.start_minute)
        assert placed[0].end_minute <= placed[1].start_minute

    def test_two_assistants_are_not_sent_to_one_customer_at_once(
        self, config: PlanningConfig
    ) -> None:
        """The constraint holds across assistants, not just within one.

        Notes:
            **This is the case the per-assistant no-overlap cannot catch.**
            Nothing in it stops assistant A and assistant B being sent to the
            same living room at the same hour — and with two assistants free
            and a tight window, that is exactly what a travel-minimising
            objective would choose. For the customer it is the visible failure:
            they open the door twice.
        """
        requirements = [
            _requirement("r1", customer_id="cust-1", window=(9 * 60, 13 * 60)),
            _requirement("r2", customer_id="cust-1", window=(9 * 60, 13 * 60)),
        ]
        solution = _solve(
            config, requirements, [_hca("hca-1"), _hca("hca-2")], radius_km=200
        )

        assert solution.is_complete() is True
        placed = sorted(solution.assignments, key=lambda entry: entry.start_minute)
        assert placed[0].end_minute <= placed[1].start_minute

    def test_visits_to_different_customers_may_run_concurrently(
        self, config: PlanningConfig
    ) -> None:
        """The constraint is per customer, not a global serialisation.

        Notes:
            Two assistants working two customers at the same hour is the normal
            case, and a constraint that forbade it would halve the agency's
            capacity.
        """
        requirements = [
            _requirement("r1", customer_id="cust-1", window=(9 * 60, 11 * 60)),
            _requirement("r2", customer_id="cust-2", window=(9 * 60, 11 * 60)),
        ]
        solution = _solve(config, requirements, [_hca("hca-1"), _hca("hca-2")])

        assert solution.is_complete() is True
        assert len(solution.assignments_by_hca()) == 2

    def test_the_same_customer_on_two_days_never_clashes(
        self, config: PlanningConfig
    ) -> None:
        """Visits on different days are grouped apart.

        Notes:
            Pairing every visit a customer receives all week would add
            constraints that can never bind, and on a busy customer that is a
            lot of them.
        """
        requirements = [
            _requirement("r1", customer_id="cust-1", day=MONDAY),
            _requirement("r2", customer_id="cust-1", day=date(2026, 8, 4)),
        ]
        solution = _solve(config, requirements, [_hca()])

        assert solution.is_complete() is True

    def test_an_impossible_pair_leaves_one_unplaced(
        self, config: PlanningConfig
    ) -> None:
        """Two visits that cannot be serialised leave one behind.

        Notes:
            Two hours of work in a two-hour window looks like an exact fit, and
            would be if the assistants were already there. They are not: the
            journey from home eats into the window, so the second visit would
            have to run past its end. Extra assistants do not help, because the
            customer can only be visited once at a time.
        """
        requirements = [
            _requirement(
                "r1", customer_id="cust-1", window=(9 * 60, 11 * 60), duration=60
            ),
            _requirement(
                "r2", customer_id="cust-1", window=(9 * 60, 11 * 60), duration=60
            ),
        ]
        solution = _solve(config, requirements, [_hca("hca-1"), _hca("hca-2")])

        assert len(solution.unassigned_requirement_ids) == 1


class TestFeasibilityDiagnosis:
    """Tests for the explanation a failed run carries."""

    @pytest.fixture
    def service(self, config: PlanningConfig) -> PlanningService:
        """Return a planning service over stand-in stores.

        Args:
            config (PlanningConfig): The working-day bounds.

        Returns:
            PlanningService: The service under test.

        Notes:
            The diagnosis reads nothing but the configuration and its
            arguments, so the repositories are never touched.
        """
        return PlanningService(
            runs=AsyncMock(),
            interventions=AsyncMock(),
            quotes=AsyncMock(),
            customers=AsyncMock(),
            hcas=AsyncMock(),
            settings=AsyncMock(),
            config=config,
        )

    def test_out_of_radius_work_is_named_as_such(
        self, service: PlanningService
    ) -> None:
        """The reason a manager can act on is the one reported.

        Notes:
            "No assistant lives within 20 km of this customer" tells a manager
            to widen the radius or hire; "infeasible" tells them nothing.
        """
        requirement = _requirement("r1", FAR_AWAY)
        explained = service.explain_unplaced(
            ["r1"],
            [requirement],
            [_hca()],
            PlanningSettings(max_intervention_radius_km=20.0),
        )

        assert explained[0].reason is UnplacedReason.OUT_OF_RADIUS
        assert "km away" in (explained[0].detail or "")

    def test_an_absent_workforce_is_named_as_such(
        self, service: PlanningService
    ) -> None:
        """Work nobody is available for reports the availability, not the radius."""
        away = _hca(
            availability=[
                {
                    "hca_id": "hca-1",
                    "start_date": MONDAY,
                    "end_date": MONDAY,
                    "kind": AvailabilityKind.DAY_OFF,
                }
            ]
        )
        explained = service.explain_unplaced(
            ["r1"],
            [_requirement("r1", NEARBY)],
            [away],
            PlanningSettings(max_intervention_radius_km=200.0),
        )

        assert explained[0].reason is UnplacedReason.NO_ASSISTANT_AVAILABLE

    def test_a_window_shorter_than_the_service_never_reaches_a_solve(
        self, service: PlanningService
    ) -> None:
        """A two-hour service in a one-hour window cannot even be built.

        Notes:
            There is no ``WINDOW_TOO_SHORT`` reason, and this is why: the
            requirement model refuses the state outright, so the planner never
            sees it and a diagnosis for it would be a branch nothing runs.
        """
        with pytest.raises(MTRequirementInvalidWindow):
            _requirement("r1", NEARBY, window=(9 * 60, 10 * 60), duration=120)

    def test_a_window_outside_the_working_day_is_named_as_such(
        self, service: PlanningService
    ) -> None:
        """Work quoted for 06:00 cannot be planned into a 09:00 day."""
        requirement = _requirement("r1", NEARBY, window=(6 * 60, 8 * 60), duration=60)
        explained = service.explain_unplaced(
            ["r1"],
            [requirement],
            [_hca()],
            PlanningSettings(max_intervention_radius_km=200.0),
        )

        assert explained[0].reason is UnplacedReason.OUTSIDE_WORKING_DAY

    def test_a_customer_clash_is_named_as_such(self, service: PlanningService) -> None:
        """Two visits that cannot share their window report the clash."""
        requirements = [
            _requirement(
                "r1",
                NEARBY,
                customer_id="cust-1",
                window=(9 * 60, 10 * 60),
                duration=60,
            ),
            _requirement(
                "r2",
                NEARBY,
                customer_id="cust-1",
                window=(9 * 60, 10 * 60),
                duration=60,
            ),
        ]
        explained = service.explain_unplaced(
            ["r2"],
            requirements,
            [_hca()],
            PlanningSettings(max_intervention_radius_km=200.0),
        )

        assert explained[0].reason is UnplacedReason.CUSTOMER_CONFLICT

    def test_the_radius_is_reported_before_the_slot(
        self, service: PlanningService
    ) -> None:
        """Both are true of unreachable work; the actionable one wins.

        Notes:
            A visit nobody can reach also has no feasible slot. Reporting the
            second would be accurate and useless.
        """
        explained = service.explain_unplaced(
            ["r1"],
            [_requirement("r1", FAR_AWAY)],
            [_hca()],
            PlanningSettings(max_intervention_radius_km=20.0),
        )

        assert explained[0].reason is not UnplacedReason.NO_FEASIBLE_SLOT

    def test_an_unknown_identifier_is_skipped_not_fatal(
        self, service: PlanningService
    ) -> None:
        """Diagnosing a failure must not itself fail."""
        explained = service.explain_unplaced(
            ["ghost"],
            [_requirement("r1")],
            [_hca()],
            PlanningSettings(max_intervention_radius_km=200.0),
        )

        assert explained == []

    def test_every_record_describes_itself(self, service: PlanningService) -> None:
        """The report is a sentence, not a pair of identifiers."""
        explained = service.explain_unplaced(
            ["r1"],
            [_requirement("r1", FAR_AWAY)],
            [_hca()],
            PlanningSettings(max_intervention_radius_km=20.0),
        )

        described = explained[0].describe()
        assert "Service r1" in described
        assert str(MONDAY) in described
