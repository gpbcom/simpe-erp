from __future__ import annotations

# Standard library imports
from datetime import date, timedelta
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.configuration.planning_config import PlanningConfig
from models.enums import AvailabilityKind, ContractType, UnplacedReason, Weekday
from models.geo.geo_point import GeoPoint
from models.people.hca import Hca
from models.planning.intervention.exceptions import MTRequirementInvalidWindow
from models.planning.intervention.intervention_requirement import InterventionRequirement
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
    working_weekdays: Optional[List[str]] = None,
) -> Hca:
    """Build an assistant whose home is already geocoded.

    Args:
        hca_id (str): The identifier to assign.
        home (GeoPoint): Where they live.
        availability (Optional[List[Dict[str, object]]]): Absences to record.
        working_weekdays (Optional[List[str]]): The days of the week they work.
            Defaults to every day, so a test that says nothing about the
            working week is not silently constrained by one.

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
        driving_license={"categories": ["B"]},
        availability=availability or [],
        working_weekdays=(
            working_weekdays if working_weekdays else list(Weekday.values())
        ),
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
    settings: Optional[PlanningSettings] = None,
):
    """Run the solver over a scenario with a given radius.

    Args:
        config (PlanningConfig): The planning rules.
        requirements (List[InterventionRequirement]): The work.
        assistants (List[Hca]): The workforce.
        radius_km (float): The intervention radius to apply.
        settings (Optional[PlanningSettings]): The stored rules to solve
            under. Defaults to the shipped working day at ``radius_km``, which
            is what a test that only cares about distance wants.

    Returns:
        PlanningSolution: What the solver produced.
    """
    service = PlanningService(
        runs=MagicMock(),
        interventions=MagicMock(),
        quotes=MagicMock(),
        customers=MagicMock(),
        hcas=MagicMock(),
        types=MagicMock(),
        settings=MagicMock(),
        config=config,
    )
    # The travel tables live on the service now, keyed by assistant, and every
    # solve builds its own first.
    service.build_travel(assistants, requirements)
    return service.solve(
        requirements,
        assistants,
        settings
        if settings
        else PlanningSettings(max_intervention_radius_km=radius_km),
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


class TestWorkingWeekdays:
    """Tests for the recurring days an assistant does not work."""

    def test_work_on_a_day_they_never_work_is_refused(
        self, config: PlanningConfig
    ) -> None:
        """A day off in the week is a hard constraint, not a preference.

        Notes:
            The only assistant is within the radius, qualified and not absent.
            The visit goes unplaced solely because it falls on a day they do
            not work — which is what makes this constraint load-bearing rather
            than a filter the solver could pay its way past.
        """
        monday_off = _hca(
            working_weekdays=["tuesday", "wednesday", "thursday", "friday"]
        )
        solution = _solve(
            config, [_requirement("r1", NEARBY, day=MONDAY)], [monday_off]
        )

        assert solution.is_complete() is False
        assert solution.unassigned_requirement_ids == ["r1"]

    def test_work_on_a_day_they_do_work_is_placed(self, config: PlanningConfig) -> None:
        """The constraint bites on the day off, and only on it."""
        monday_off = _hca(
            working_weekdays=["tuesday", "wednesday", "thursday", "friday"]
        )
        tuesday = MONDAY + timedelta(days=1)
        solution = _solve(
            config, [_requirement("r1", NEARBY, day=tuesday)], [monday_off]
        )

        assert solution.is_complete() is True

    def test_the_work_goes_to_the_colleague_who_works_that_day(
        self, config: PlanningConfig
    ) -> None:
        """A day off moves work to somebody else rather than dropping it.

        Notes:
            The realistic case, and the one a rota is for: two assistants who
            are equally close, and only one of whom works Mondays.
        """
        monday_off = _hca(
            "hca-1", working_weekdays=["tuesday", "wednesday", "thursday"]
        )
        works_mondays = _hca("hca-2", working_weekdays=["monday", "tuesday"])
        solution = _solve(
            config,
            [_requirement("r1", NEARBY, day=MONDAY)],
            [monday_off, works_mondays],
        )

        assert solution.is_complete() is True
        assert solution.assignments[0].hca_id == "hca-2"

    def test_a_day_off_and_an_absence_are_both_enforced(
        self, config: PlanningConfig
    ) -> None:
        """Neither half of the rule shadows the other.

        Notes:
            One assistant does not work Mondays; the other works Mondays but is
            on leave this one. Both are within the radius, and the visit still
            cannot be placed — so neither check is quietly standing in for the
            other.
        """
        monday_off = _hca("hca-1", working_weekdays=["tuesday", "wednesday"])
        on_leave = _hca(
            "hca-2",
            working_weekdays=["monday", "tuesday"],
            availability=[
                {
                    "hca_id": "hca-2",
                    "start_date": MONDAY,
                    "end_date": MONDAY,
                    "kind": AvailabilityKind.SICK_LEAVE,
                }
            ],
        )
        solution = _solve(
            config, [_requirement("r1", NEARBY, day=MONDAY)], [monday_off, on_leave]
        )

        assert solution.is_complete() is False


class TestConfigurableWorkingDay:
    """Tests for the working day and lunch window a manager owns."""

    def test_a_visit_outside_the_stored_day_is_refused(
        self, config: PlanningConfig
    ) -> None:
        """The bounds come from the settings, not from the config file.

        Notes:
            The configuration still says 09:00-20:00. The stored settings say
            the day ends at 17:00, and an 18:00 visit is refused — which is
            only true if the solver reads the settings. Before this change it
            read ``config`` and the visit would have been placed.
        """
        settings = PlanningSettings(
            max_intervention_radius_km=200.0,
            day_start_minute=9 * 60,
            day_end_minute=17 * 60,
        )
        late = _requirement("r1", NEARBY, window=(18 * 60, 19 * 60), duration=60)
        solution = _solve(config, [late], [_hca()], settings=settings)

        assert solution.is_complete() is False

    def test_a_widened_day_places_work_the_default_would_refuse(
        self, config: PlanningConfig
    ) -> None:
        """Moving the day is what makes it configurable, not just narrower.

        Notes:
            An 08:00 visit falls outside the shipped 09:00 start. A manager who
            has moved the day to 07:00 gets it placed, without a deployment.
        """
        early = _requirement("r1", NEARBY, window=(8 * 60, 9 * 60), duration=60)
        refused = _solve(config, [early], [_hca()])
        assert refused.is_complete() is False

        settings = PlanningSettings(
            max_intervention_radius_km=200.0,
            day_start_minute=7 * 60,
            day_end_minute=20 * 60,
        )
        allowed = _solve(config, [early], [_hca()], settings=settings)

        assert allowed.is_complete() is True

    def test_the_lunch_break_is_reserved_inside_the_stored_window(
        self, config: PlanningConfig
    ) -> None:
        """The break falls in the window a manager chose, not the shipped one.

        Notes:
            One visit, pinned to 09:00-10:00 by its own window, at the
            assistant's own address so travel cannot confound the arithmetic.
            The two solves differ in nothing but the stored lunch window.

            Moved to 09:00-10:00, the break has nowhere to go but on top of the
            visit, and the work goes unplaced. Left at the shipped 11:30-14:30
            the break sits well clear and the same visit is placed. A solver
            still reading the configuration file would place it both times.
        """
        pinned = _requirement("r1", HOME, window=(9 * 60, 10 * 60), duration=60)

        collides = _solve(
            config,
            [pinned],
            [_hca()],
            settings=PlanningSettings(
                max_intervention_radius_km=200.0,
                lunch_break_minutes=60,
                lunch_window_start_minute=9 * 60,
                lunch_window_end_minute=10 * 60,
            ),
        )
        assert collides.is_complete() is False

        clear = _solve(
            config,
            [pinned],
            [_hca()],
            settings=PlanningSettings(max_intervention_radius_km=200.0),
        )

        assert clear.is_complete() is True
        assert clear.assignments[0].start_minute == 9 * 60


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
            types=AsyncMock(),
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

    def test_a_day_nobody_works_is_named_as_such(
        self, service: PlanningService
    ) -> None:
        """A recurring day off reads differently from a week's leave.

        Notes:
            **The distinction is the point of the reason existing.** "Nobody
            works a Monday" is a rota or a recruitment decision; "everybody is
            absent" resolves itself when they come back. Reporting the second
            when the first is true sends a manager through absence records
            looking for a day nobody ever agreed to work.
        """
        never_mondays = _hca(
            working_weekdays=["tuesday", "wednesday", "thursday", "friday"]
        )
        explained = service.explain_unplaced(
            ["r1"],
            [_requirement("r1", NEARBY)],
            [never_mondays],
            PlanningSettings(max_intervention_radius_km=200.0),
        )

        assert explained[0].reason is UnplacedReason.NOT_A_WORKING_DAY
        assert "monday" in (explained[0].detail or "")

    def test_a_day_nobody_works_is_reported_before_an_absence(
        self, service: PlanningService
    ) -> None:
        """The more specific of the two overlapping reasons wins.

        Notes:
            The assistant neither works Mondays nor is available on this one.
            Both readings are true; only the first names something to change.
        """
        both = _hca(
            working_weekdays=["tuesday", "wednesday"],
            availability=[
                {
                    "hca_id": "hca-1",
                    "start_date": MONDAY,
                    "end_date": MONDAY,
                    "kind": AvailabilityKind.SICK_LEAVE,
                }
            ],
        )
        explained = service.explain_unplaced(
            ["r1"],
            [_requirement("r1", NEARBY)],
            [both],
            PlanningSettings(max_intervention_radius_km=200.0),
        )

        assert explained[0].reason is UnplacedReason.NOT_A_WORKING_DAY

    def test_the_working_day_reported_is_the_stored_one(
        self, service: PlanningService
    ) -> None:
        """The report quotes the hours a manager set, not the shipped ones.

        Notes:
            A report naming 09:00-20:00 while the agency runs 08:00-17:00 sends
            somebody to widen a window that is already as wide as the rule
            allows. The minute is printed too: a day ending at 17:30 reported
            as "17:00" hides a half-hour that was never there.
        """
        settings = PlanningSettings(
            max_intervention_radius_km=200.0,
            day_start_minute=8 * 60,
            day_end_minute=17 * 60 + 30,
        )
        late = _requirement("r1", NEARBY, window=(18 * 60, 19 * 60), duration=60)
        explained = service.explain_unplaced(["r1"], [late], [_hca()], settings)

        assert explained[0].reason is UnplacedReason.OUTSIDE_WORKING_DAY
        assert "08:00–17:30" in (explained[0].detail or "")

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


class TestReproducibility:
    """Tests that the same week plans the same way twice."""

    def test_the_solver_is_configured_for_a_reproducible_search(self) -> None:
        """**Three settings together, and a seed alone is not enough.**

        Notes:
            Fixing ``random_seed`` was tried first and still gave 502, 495 and
            502 travel minutes over three runs of one input, because
            ``max_time_in_seconds`` halts the search wherever elapsed time
            happens to land — a loaded machine explores less. The deterministic
            budget is what actually stops it at the same place, and a single
            worker stops parallel searches racing to the incumbent.

            Asserted on the configuration rather than by solving three times:
            a test that ran the solver repeatedly would take a minute and would
            still only sample the non-determinism it is meant to exclude.

            Built from the shipped defaults, not from this module's fixture:
            the fixture shortens the budget so the suite stays fast, and
            asserting against it would test the fixture.
        """
        shipped = PlanningConfig()

        assert shipped.solver_workers == 1
        assert shipped.solver_seed >= 0
        assert shipped.solver_deterministic_budget > 0

    def test_the_wall_clock_limit_is_a_net_not_a_budget(self) -> None:
        """It must be loose enough that the deterministic budget binds first.

        Notes:
            If the clock fires it is the clock that decided where to stop, and
            the run is no longer reproducible.

            **The shipped defaults failed this, and the failure was the bug.**
            A net of 600.0 against a budget of 100.0 stops every solve at
            around four tenths of its allowance, and a 95-visit week came back
            one visit short at status FEASIBLE — which is indistinguishable,
            from the outside, from a week that genuinely does not fit.

            Twenty rather than ten, and measured rather than guessed: the
            sizing table in ``backend/conf/app.yaml`` records 40.0 units
            costing 576 seconds at eight workers, so a unit is worth about
            fourteen and a half seconds of wall clock and ten times the budget
            is not enough to spend it. The Helm chart carries the same floor,
            so a cluster cannot be configured into this either.
        """
        shipped = PlanningConfig()

        assert shipped.solver_time_limit_seconds >= (
            shipped.solver_deterministic_budget * 20
        )

    def test_the_same_input_plans_identically_twice(
        self, config: PlanningConfig
    ) -> None:
        """The promise, end to end on a small instance.

        Args:
            config (PlanningConfig): The planning rules.

        Notes:
            Small on purpose — two assistants and six visits solve in well
            under a second, so this can assert the actual guarantee rather than
            its configuration without costing the suite a minute.
        """
        requirements = [_requirement(f"r{index}", NEARBY) for index in range(6)]
        assistants = [_hca("hca-1"), _hca("hca-2", home=NEARBY)]

        first = _solve(config, requirements, assistants)
        second = _solve(config, requirements, assistants)

        assert first.total_travel_minutes == second.total_travel_minutes
        assert [
            (entry.requirement_id, entry.hca_id, entry.start_minute)
            for entry in sorted(first.assignments, key=lambda e: e.requirement_id)
        ] == [
            (entry.requirement_id, entry.hca_id, entry.start_minute)
            for entry in sorted(second.assignments, key=lambda e: e.requirement_id)
        ]
