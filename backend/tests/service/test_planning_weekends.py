from __future__ import annotations

# Standard library imports
from datetime import date
from typing import List
from unittest.mock import MagicMock

# Third-party imports
import pytest

# First-party imports
from models.configuration.planning_config import PlanningConfig
from models.enums import ContractType, UnplacedReason, Weekday
from models.geo.geo_point import GeoPoint
from models.people.hca import Hca
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)
from models.settings.planning_settings import PlanningSettings
from service.planning.plannings import PlanningService

# 2026-08-03 is a Monday, so the week runs Monday 3rd to Sunday 9th.
MONDAY = date(2026, 8, 3)
SATURDAY = date(2026, 8, 8)
SUNDAY = date(2026, 8, 9)
HOME = GeoPoint(latitude=48.8566, longitude=2.3522)
NEARBY = GeoPoint(latitude=48.8600, longitude=2.3550)


@pytest.fixture
def config() -> PlanningConfig:
    """Return a planning configuration with a short solver budget.

    Returns:
        PlanningConfig: A two-second budget.
    """
    return PlanningConfig(solver_time_limit_seconds=2.0)


def _hca(working_weekdays: List[Weekday], hca_id: str = "hca-1") -> Hca:
    """Build an assistant working a given week.

    Args:
        working_weekdays (List[Weekday]): The days they work at all.
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
        working_weekdays=working_weekdays,
    )


def _requirement(day: date) -> InterventionRequirement:
    """Build one ungated, reachable visit on a given day.

    Args:
        day (date): The day the work happens.

    Returns:
        InterventionRequirement: The work.
    """
    return InterventionRequirement(
        id="req-1",
        quote_line_id="line-1",
        customer_id="customer-1",
        name="Aide a la toilette",
        intervention_type_id="type-1",
        day=day,
        window_start_minute=9 * 60,
        window_end_minute=20 * 60,
        duration_minutes=60,
        location=NEARBY,
    )


def _service(config: PlanningConfig) -> PlanningService:
    """Return a planning service over stand-in repositories.

    Args:
        config (PlanningConfig): The planning rules.

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
        config=config,
    )


def _place(config: PlanningConfig, day: date, workforce: List[Hca]) -> List[str]:
    """Solve one visit and return who was given it.

    Args:
        config (PlanningConfig): The planning rules.
        day (date): The day the visit happens.
        workforce (List[Hca]): The people available.

    Returns:
        List[str]: The identifiers assigned work.
    """
    service = _service(config)
    requirements = [_requirement(day)]
    service.build_travel(workforce, requirements)
    solution = service.solve(
        requirements, workforce, PlanningSettings(max_intervention_radius_km=200.0)
    )
    return [assignment.hca_id for assignment in solution.assignments]


class TestWeekendsAreOrdinaryWorkingDays:
    """Tests that Saturday and Sunday are days like any other.

    Notes:
        **Nothing ever refused them.** `Weekday` carries all seven,
        `WorkingDaysRequest` accepts any of them, and the planner asks
        `works_on_weekday` rather than checking for a weekend. What made them
        look barred is that `Hca.DEFAULT_WORKING_WEEKDAYS` is Monday-to-Friday,
        so every record that has never been edited shows the two of them
        greyed — a default reading as a rule.

        These pin the distinction, because "the default is Mon-Fri" and
        "weekends cannot be worked" are indistinguishable on screen and only
        one of them is true.
    """

    @pytest.mark.parametrize(
        ("day", "weekday"),
        [(SATURDAY, Weekday.SATURDAY), (SUNDAY, Weekday.SUNDAY)],
    )
    def test_a_weekend_worker_is_given_weekend_work(
        self, config: PlanningConfig, day: date, weekday: Weekday
    ) -> None:
        """Somebody whose declared week is the weekend gets the visit.

        Args:
            config (PlanningConfig): The planning rules.
            day (date): The weekend day the visit falls on.
            weekday (Weekday): The day they declare they work.
        """
        assert _place(config, day, [_hca([weekday])]) == ["hca-1"]

    def test_the_default_week_does_not_cover_the_weekend(
        self, config: PlanningConfig
    ) -> None:
        """Which is what makes the weekend look unavailable, and is only a default.

        Args:
            config (PlanningConfig): The planning rules.
        """
        standard = _hca(list(Hca.DEFAULT_WORKING_WEEKDAYS))

        assert Weekday.SATURDAY not in standard.working_weekdays
        assert _place(config, SATURDAY, [standard]) == []

    def test_the_same_person_editing_their_week_changes_the_answer(
        self, config: PlanningConfig
    ) -> None:
        """**The end of the chain the manager's dialog starts.**

        Args:
            config (PlanningConfig): The planning rules.

        Notes:
            The same record, unplannable on Saturday and then plannable,
            decided by nothing but the week somebody selected.
        """
        assert _place(config, SATURDAY, [_hca(list(Hca.DEFAULT_WORKING_WEEKDAYS))]) == []
        assert _place(
            config, SATURDAY, [_hca([*Hca.DEFAULT_WORKING_WEEKDAYS, Weekday.SATURDAY])]
        ) == ["hca-1"]

    def test_a_weekend_only_worker_is_left_out_on_a_weekday(
        self, config: PlanningConfig
    ) -> None:
        """The rule runs both ways, which is what makes it a rota.

        Args:
            config (PlanningConfig): The planning rules.
        """
        assert _place(config, MONDAY, [_hca([Weekday.SATURDAY, Weekday.SUNDAY])]) == []

    def test_the_weekday_mapping_is_not_off_by_one(self) -> None:
        """Saturday is ISO 6 and Sunday ISO 7, and an off-by-one is silent.

        Notes:
            `works_on_weekday` converts through `Weekday.from_iso_weekday`. A
            mapping shifted by one would schedule the weekend crew on Friday
            and Saturday, which looks like a working rota rather than a bug.
        """
        weekend_worker = _hca([Weekday.SATURDAY, Weekday.SUNDAY])

        assert weekend_worker.works_on_weekday(SATURDAY) is True
        assert weekend_worker.works_on_weekday(SUNDAY) is True
        assert weekend_worker.works_on_weekday(date(2026, 8, 7)) is False

    def test_unplaced_weekend_work_is_reported_as_a_rota_decision(
        self, config: PlanningConfig
    ) -> None:
        """"Nobody works Saturdays" is a recruitment answer, not an absence.

        Args:
            config (PlanningConfig): The planning rules.
        """
        explained = _service(config).explain_unplaced(
            ["req-1"],
            [_requirement(SATURDAY)],
            [_hca(list(Hca.DEFAULT_WORKING_WEEKDAYS))],
            PlanningSettings(max_intervention_radius_km=200.0),
        )

        assert explained[0].reason is UnplacedReason.NOT_A_WORKING_DAY
