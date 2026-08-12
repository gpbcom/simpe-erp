from __future__ import annotations

# Standard library imports
from datetime import date
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.configuration.planning_config import PlanningConfig
from models.enums import ContractType, UnplacedReason
from models.geo.geo_point import GeoPoint
from models.people.hca.certification import Certification
from models.people.hca import Hca
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)
from models.planning.planning_run.planning_solution import PlanningSolution
from models.settings.planning_settings import PlanningSettings
from service.planning.plannings import PlanningService

MONDAY = date(2026, 8, 3)
HOME = GeoPoint(latitude=48.8566, longitude=2.3522)
NEARBY = GeoPoint(latitude=48.8600, longitude=2.3550)


@pytest.fixture
def config() -> PlanningConfig:
    """Return a planning configuration with a short solver budget.

    Returns:
        PlanningConfig: 09:00-20:00, two seconds to solve.
    """
    return PlanningConfig(solver_time_limit_seconds=2.0)


def _hca(
    hca_id: str = "hca-1",
    certifications: Optional[List[Certification]] = None,
    field_employee: bool = True,
) -> Hca:
    """Build an assistant whose home is already geocoded.

    Args:
        hca_id (str): The identifier to assign.
        certifications (Optional[List[Certification]]): Qualifications held.
        field_employee (bool): Whether they may be placed on a planning.

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
        certifications=certifications or [],
        field_employee=field_employee,
    )


def _requirement(
    requirement_id: str = "req-1",
    codes: Optional[List[str]] = None,
    day: date = MONDAY,
) -> InterventionRequirement:
    """Build one piece of work, optionally gated on a qualification.

    Args:
        requirement_id (str): The identifier to assign.
        codes (Optional[List[str]]): Certification codes it requires.
        day (date): The day it happens.

    Returns:
        InterventionRequirement: The work.
    """
    return InterventionRequirement(
        id=requirement_id,
        quote_line_id=requirement_id,
        customer_id=f"customer-{requirement_id}",
        name="Soin",
        intervention_type_id="type-1",
        day=day,
        window_start_minute=9 * 60,
        window_end_minute=20 * 60,
        duration_minutes=60,
        location=NEARBY,
        required_certification_codes=codes or [],
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
        teams=AsyncMock(),
        config=config,
    )


def _solve(
    config: PlanningConfig,
    requirements: List[InterventionRequirement],
    assistants: List[Hca],
) -> PlanningSolution:
    """Run the solver over a scenario with a wide-open radius.

    Args:
        config (PlanningConfig): The planning rules.
        requirements (List[InterventionRequirement]): The work.
        assistants (List[Hca]): The workforce.

    Returns:
        PlanningSolution: What the solver produced.
    """
    service = _service(config)
    service.build_travel(assistants, requirements)
    return service.solve(
        requirements,
        assistants,
        PlanningSettings(max_intervention_radius_km=200.0),
    )


class TestCertificationConstraint:
    """Tests for the rule that only a qualified person takes gated work."""

    def test_unqualified_work_goes_to_anybody(self, config: PlanningConfig) -> None:
        """Work requiring nothing is the common case and stays cheap."""
        solution = _solve(config, [_requirement()], [_hca()])

        assert solution.unassigned_requirement_ids == []

    def test_only_the_qualified_assistant_is_given_gated_work(
        self, config: PlanningConfig
    ) -> None:
        """A visit needing a diploma goes to the one person who holds it."""
        qualified = _hca(
            "hca-1", certifications=[Certification(name="DEAES", code="DEAES")]
        )
        unqualified = _hca("hca-2")

        solution = _solve(
            config, [_requirement(codes=["DEAES"])], [qualified, unqualified]
        )

        assert solution.unassigned_requirement_ids == []
        assert solution.assignments[0].hca_id == "hca-1"

    def test_work_nobody_qualifies_for_goes_unplaced(
        self, config: PlanningConfig
    ) -> None:
        """A hard constraint, not a preference.

        Notes:
            The solver cannot pay its way past this the way it can pay for
            travel. Sending somebody unqualified is worse than sending nobody,
            and the run that follows fails saying which qualification was
            missing.
        """
        solution = _solve(config, [_requirement(codes=["DEAES"])], [_hca()])

        assert solution.unassigned_requirement_ids == ["req-1"]

    def test_every_required_code_is_needed(self, config: PlanningConfig) -> None:
        """Holding one of two required diplomas is not enough.

        Notes:
            Reading the list as "one of these" would send somebody to a visit
            half qualified, which is the failure the whole field prevents.
        """
        partly = _hca(
            "hca-1", certifications=[Certification(name="DEAES", code="DEAES")]
        )

        solution = _solve(config, [_requirement(codes=["DEAES", "SST"])], [partly])

        assert solution.unassigned_requirement_ids == ["req-1"]

    def test_a_lapsed_qualification_does_not_count(
        self, config: PlanningConfig
    ) -> None:
        """Expiry is judged on the day of the visit, not on the day of the solve.

        Notes:
            A plan built a fortnight ahead must not hand work to somebody whose
            certificate lapses before they get there.
        """
        lapsing = _hca(
            "hca-1",
            certifications=[Certification(name="SST", code="SST", expires_on=MONDAY)],
        )

        assert (
            _solve(
                config, [_requirement(codes=["SST"], day=MONDAY)], [lapsing]
            ).unassigned_requirement_ids
            == []
        )
        assert _solve(
            config,
            [_requirement(codes=["SST"], day=date(2026, 8, 4))],
            [lapsing],
        ).unassigned_requirement_ids == ["req-1"]

    def test_an_untyped_qualification_does_not_count(
        self, config: PlanningConfig
    ) -> None:
        """A free-text name is not a claim the agency can match against.

        Notes:
            Matching on the name would let a spelling decide who is qualified.
        """
        typed_by_hand = _hca("hca-1", certifications=[Certification(name="DEAES")])

        solution = _solve(config, [_requirement(codes=["DEAES"])], [typed_by_hand])

        assert solution.unassigned_requirement_ids == ["req-1"]


class TestCertificationDiagnosis:
    """Tests for what a manager is told when nobody is qualified."""

    def test_the_missing_qualification_is_named(self, config: PlanningConfig) -> None:
        """The reason names the code and how many people were considered."""
        requirement = _requirement(codes=["DEAES"])
        assistants = [_hca()]

        explained = _service(config).explain_unplaced(
            ["req-1"],
            [requirement],
            assistants,
            PlanningSettings(max_intervention_radius_km=200.0),
        )

        assert explained[0].reason is UnplacedReason.MISSING_CERTIFICATION
        assert "DEAES" in explained[0].detail

    def test_it_is_reported_before_anything_geographical(
        self, config: PlanningConfig
    ) -> None:
        """A visit nobody is qualified for is also out of radius; say the first.

        Notes:
            **This ordering is the point.** Reporting the distance would send a
            manager to widen a radius that was never the problem, while "nobody
            here holds DEAES" names a hire, a training course, or a requirement
            that was wrong.
        """
        far_away = _hca("hca-1")
        requirement = _requirement(codes=["DEAES"])

        explained = _service(config).explain_unplaced(
            ["req-1"],
            [requirement],
            [far_away],
            PlanningSettings(max_intervention_radius_km=0.1),
        )

        assert explained[0].reason is UnplacedReason.MISSING_CERTIFICATION

    def test_later_reasons_only_consider_the_qualified(
        self, config: PlanningConfig
    ) -> None:
        """ "All 6 assistants are absent" is wrong when only one was qualified.

        Notes:
            Reporting a count over the whole workforce sends a manager to look
            at the rota when the answer was the rota of one person.
        """
        qualified_but_far = _hca(
            "hca-1", certifications=[Certification(name="DEAES", code="DEAES")]
        )
        others = [_hca(f"hca-{index}") for index in range(2, 8)]

        explained = _service(config).explain_unplaced(
            ["req-1"],
            [_requirement(codes=["DEAES"])],
            [qualified_but_far, *others],
            PlanningSettings(max_intervention_radius_km=0.1),
        )

        assert explained[0].reason is UnplacedReason.OUT_OF_RADIUS


class TestFieldEmployeeFilter:
    """Tests for who the planner is allowed to schedule at all."""

    def test_a_field_employee_is_kept(self, config: PlanningConfig) -> None:
        """The default is what every record that predates the flag already was."""
        assert _service(config)._field_employees([_hca()]) == [_hca()]

    def test_an_office_based_person_is_held_back(self, config: PlanningConfig) -> None:
        """Somebody who does not go out is left out of the run."""
        office = _hca("hca-2", field_employee=False)

        assert _service(config)._field_employees([_hca(), office]) == [_hca()]

    def test_an_entirely_office_based_workforce_yields_nobody(
        self, config: PlanningConfig
    ) -> None:
        """An empty pool is a legitimate, loudly-logged answer.

        Notes:
            The solver reports every requirement unassigned rather than
            raising, and the run fails with that. What must not happen is the
            filter silently falling back to the whole workforce.
        """
        office = [_hca("hca-1", field_employee=False)]

        assert _service(config)._field_employees(office) == []
