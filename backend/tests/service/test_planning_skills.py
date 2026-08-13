from __future__ import annotations

# Standard library imports
from datetime import date
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.configuration.planning_config import PlanningConfig
from models.enums import ContractType, UnplacedReason, RegistrationStatus
from models.geo.geo_point import GeoPoint
from models.people.hca.certification import Certification
from models.people.hca import Hca
from models.people.hca.skill import Skill
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)
from models.people.customer import Customer
from models.planning.planning_run.planning_solution import PlanningSolution
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
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
    skills: Optional[List[Skill]] = None,
    certifications: Optional[List[Certification]] = None,
) -> Hca:
    """Build an assistant whose home is already geocoded.

    Args:
        hca_id (str): The identifier to assign.
        skills (Optional[List[Skill]]): Skills they have declared.
        certifications (Optional[List[Certification]]): Qualifications held.

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
        skills=skills or [],
        certifications=certifications or [],
    )


def _requirement(
    requirement_id: str = "req-1",
    skill_codes: Optional[List[str]] = None,
    certification_codes: Optional[List[str]] = None,
    day: date = MONDAY,
) -> InterventionRequirement:
    """Build one piece of work, optionally gated on a skill.

    Args:
        requirement_id (str): The identifier to assign.
        skill_codes (Optional[List[str]]): Skill codes it requires.
        certification_codes (Optional[List[str]]): Certification codes.
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
        required_skill_codes=skill_codes or [],
        required_certification_codes=certification_codes or [],
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


class TestSkillConstraint:
    """Tests for the rule that only somebody who declared it takes gated work."""

    def test_ungated_work_goes_to_anybody(self, config: PlanningConfig) -> None:
        """Work requiring nothing is the common case and stays cheap."""
        solution = _solve(config, [_requirement()], [_hca()])

        assert solution.unassigned_requirement_ids == []

    def test_only_the_declared_assistant_is_given_gated_work(
        self, config: PlanningConfig
    ) -> None:
        """A visit needing a hoist goes to the one person who can use it."""
        able = _hca("hca-1", skills=[Skill(name="Leve", code="LEVE-PERSONNE")])
        unable = _hca("hca-2")

        solution = _solve(
            config, [_requirement(skill_codes=["LEVE-PERSONNE"])], [able, unable]
        )

        assert solution.unassigned_requirement_ids == []
        assert solution.assignments[0].hca_id == "hca-1"

    def test_work_nobody_declared_goes_unplaced(self, config: PlanningConfig) -> None:
        """A hard constraint, not a preference.

        Notes:
            The solver cannot pay its way past this the way it can pay for
            travel. Sending somebody who cannot use a hoist to a visit that
            needs one is worse than sending nobody.
        """
        solution = _solve(
            config, [_requirement(skill_codes=["LEVE-PERSONNE"])], [_hca()]
        )

        assert solution.unassigned_requirement_ids == ["req-1"]

    def test_every_required_code_is_needed(self, config: PlanningConfig) -> None:
        """Declaring one of two required skills is not enough."""
        partly = _hca("hca-1", skills=[Skill(name="A", code="TOILETTE")])

        solution = _solve(
            config, [_requirement(skill_codes=["TOILETTE", "ARABE"])], [partly]
        )

        assert solution.unassigned_requirement_ids == ["req-1"]

    def test_a_lapsed_declaration_does_not_count(self, config: PlanningConfig) -> None:
        """Expiry is judged on the day of the visit, not on the day of the solve."""
        lapsing = _hca(
            "hca-1", skills=[Skill(name="SST", code="SST", expires_on=MONDAY)]
        )

        assert (
            _solve(
                config, [_requirement(skill_codes=["SST"], day=MONDAY)], [lapsing]
            ).unassigned_requirement_ids
            == []
        )
        assert _solve(
            config,
            [_requirement(skill_codes=["SST"], day=date(2026, 8, 4))],
            [lapsing],
        ).unassigned_requirement_ids == ["req-1"]

    def test_an_untyped_declaration_does_not_count(
        self, config: PlanningConfig
    ) -> None:
        """A free-text name is not a claim the agency can match against."""
        typed_by_hand = _hca("hca-1", skills=[Skill(name="LEVE-PERSONNE")])

        solution = _solve(
            config, [_requirement(skill_codes=["LEVE-PERSONNE"])], [typed_by_hand]
        )

        assert solution.unassigned_requirement_ids == ["req-1"]

    def test_a_certification_does_not_satisfy_a_skill(
        self, config: PlanningConfig
    ) -> None:
        """The two lists are separate all the way into the solver.

        Notes:
            Holding a certification named ``TOILETTE`` says nothing about
            having declared the *skill* ``TOILETTE``, and treating one as the
            other would send somebody to a visit on the strength of a match
            nobody made.
        """
        certified_only = _hca(
            "hca-1", certifications=[Certification(name="T", code="TOILETTE")]
        )

        solution = _solve(
            config, [_requirement(skill_codes=["TOILETTE"])], [certified_only]
        )

        assert solution.unassigned_requirement_ids == ["req-1"]

    def test_both_requirements_must_be_met_together(
        self, config: PlanningConfig
    ) -> None:
        """A visit gated on both needs one person holding both."""
        certified_only = _hca(
            "hca-1", certifications=[Certification(name="D", code="DEAES")]
        )
        both = _hca(
            "hca-2",
            certifications=[Certification(name="D", code="DEAES")],
            skills=[Skill(name="T", code="TOILETTE")],
        )

        solution = _solve(
            config,
            [_requirement(certification_codes=["DEAES"], skill_codes=["TOILETTE"])],
            [certified_only, both],
        )

        assert solution.unassigned_requirement_ids == []
        assert solution.assignments[0].hca_id == "hca-2"


class TestSkillDiagnosis:
    """Tests for what a manager is told when nobody has declared the skill."""

    def test_the_missing_skill_is_named(self, config: PlanningConfig) -> None:
        """The reason names the code and how many people were considered."""
        explained = _service(config).explain_unplaced(
            ["req-1"],
            [_requirement(skill_codes=["LEVE-PERSONNE"])],
            [_hca()],
            PlanningSettings(max_intervention_radius_km=200.0),
        )

        assert explained[0].reason is UnplacedReason.MISSING_SKILL
        assert "LEVE-PERSONNE" in explained[0].detail

    def test_it_is_reported_before_anything_geographical(
        self, config: PlanningConfig
    ) -> None:
        """A visit nobody can do is also out of radius; say the first.

        Notes:
            Reporting the distance would send a manager to widen a radius that
            was never the problem.
        """
        explained = _service(config).explain_unplaced(
            ["req-1"],
            [_requirement(skill_codes=["LEVE-PERSONNE"])],
            [_hca()],
            PlanningSettings(max_intervention_radius_km=0.1),
        )

        assert explained[0].reason is UnplacedReason.MISSING_SKILL

    def test_a_missing_certification_is_reported_ahead_of_a_missing_skill(
        self, config: PlanningConfig
    ) -> None:
        """The order between the two is not arbitrary.

        Notes:
            A certification is obtained and a skill is merely declared, so a
            visit blocked by both is reported against the one that takes longer
            to fix. The other reading would send a manager to chase a profile
            when the real obstacle was a diploma nobody holds.
        """
        explained = _service(config).explain_unplaced(
            ["req-1"],
            [
                _requirement(
                    certification_codes=["DEAES"], skill_codes=["LEVE-PERSONNE"]
                )
            ],
            [_hca()],
            PlanningSettings(max_intervention_radius_km=200.0),
        )

        assert explained[0].reason is UnplacedReason.MISSING_CERTIFICATION

    def test_the_skill_test_narrows_the_already_qualified(
        self, config: PlanningConfig
    ) -> None:
        """It runs on the candidates the certification test left.

        Notes:
            Starting again from the whole workforce would report a skill gap
            counting people who were never eligible anyway.
        """
        certified_only = _hca(
            "hca-1", certifications=[Certification(name="D", code="DEAES")]
        )
        neither = _hca("hca-2")

        explained = _service(config).explain_unplaced(
            ["req-1"],
            [
                _requirement(
                    certification_codes=["DEAES"], skill_codes=["LEVE-PERSONNE"]
                )
            ],
            [certified_only, neither],
            PlanningSettings(max_intervention_radius_km=200.0),
        )

        assert explained[0].reason is UnplacedReason.MISSING_SKILL

    def test_later_reasons_only_consider_the_able(self, config: PlanningConfig) -> None:
        """ "All 7 assistants are out of radius" is wrong when one was able."""
        able_but_far = _hca("hca-1", skills=[Skill(name="Leve", code="LEVE-PERSONNE")])
        others = [_hca(f"hca-{index}") for index in range(2, 8)]

        explained = _service(config).explain_unplaced(
            ["req-1"],
            [_requirement(skill_codes=["LEVE-PERSONNE"])],
            [able_but_far, *others],
            PlanningSettings(max_intervention_radius_km=0.1),
        )

        assert explained[0].reason is UnplacedReason.OUT_OF_RADIUS


def _catalog_entry(codes: List[str]) -> InterventionType:
    """Build a catalogue entry requiring some skills.

    Args:
        codes (List[str]): The skill codes it requires.

    Returns:
        InterventionType: The entry.
    """
    return InterventionType(
        id="type-1",
        name="Soin",
        code="SOIN",
        service_category="necessity",
        required_skill_codes=codes,
    )


def _quote(line_codes: Optional[List[str]]) -> Quote:
    """Build one accepted quote with a single line.

    Args:
        line_codes (Optional[List[str]]): The line's own skill override, or
            ``None`` to inherit the catalogue entry.

    Returns:
        Quote: The quote.
    """
    return Quote(
        id="quote-1",
        company_id="company-1",
        team_id="team-1",
        reference="Q-1",
        customer_id="customer-1",
        status="accepted",
        lines=[
            QuoteLine(
                id="line-1",
                name="Soin",
                intervention_type_id="type-1",
                service_category="necessity",
                service_date=MONDAY,
                earliest_start="09:00:00",
                latest_end="11:00:00",
                duration_minutes=60,
                required_skill_codes=line_codes,
                # Priced, because ``build`` skips a quote that is accepted but
                # carries no figures — an unpriced line is not schedulable work.
                hourly_rate_ht="30.00",
                total_ht="30.00",
                vat_amount="1.65",
                total_ttc="31.65",
            )
        ],
    )


def _customer() -> Customer:
    """Build a geocoded, active customer the work happens at.

    Returns:
        Customer: The customer.

    Notes:
        **Active, stated rather than defaulted.** The model now defaults to
        ``PROSPECT``, whose accepted work the planner deliberately leaves out —
        so a customer built without a status would make every test here assert
        an empty plan for a reason that has nothing to do with skills.
    """
    return Customer(
        id="customer-1",
        first_name="Marie",
        last_name="Durand",
        phone_number="+33612345679",
        email="marie@example.com",
        address={
            "street": "2 rue B",
            "postal_code": "75001",
            "city": "Paris",
            "latitude": NEARBY.latitude,
            "longitude": NEARBY.longitude,
        },
        registration_status=RegistrationStatus.ACTIVE,
    )


class TestSkillRequirementBuild:
    """Tests for resolving the skill requirement once, before the solve."""

    def test_a_line_inherits_the_catalogue_entry(self, config: PlanningConfig) -> None:
        """No override means the catalogue's, resolved here rather than later.

        Notes:
            Doing it here means the solver never needs the catalog, never holds
            a second lookup table, and never has to know the inheritance rule
            exists.
        """
        built = _service(config).build(
            [_quote(None)],
            {"customer-1": _customer()},
            {"type-1": _catalog_entry(["TOILETTE"])},
            MONDAY,
            MONDAY,
        )

        assert built[0].required_skill_codes == ["TOILETTE"]

    def test_a_line_override_wins(self, config: PlanningConfig) -> None:
        """The line knows this customer; the catalogue knows the service."""
        built = _service(config).build(
            [_quote(["ARABE"])],
            {"customer-1": _customer()},
            {"type-1": _catalog_entry(["TOILETTE"])},
            MONDAY,
            MONDAY,
        )

        assert built[0].required_skill_codes == ["ARABE"]

    def test_an_empty_override_drops_the_requirement(
        self, config: PlanningConfig
    ) -> None:
        """An empty override is honoured, not treated as absent."""
        built = _service(config).build(
            [_quote([])],
            {"customer-1": _customer()},
            {"type-1": _catalog_entry(["TOILETTE"])},
            MONDAY,
            MONDAY,
        )

        assert built[0].required_skill_codes == []
        assert built[0].requires_skills() is False

    def test_a_vanished_catalogue_entry_requires_nothing(
        self, config: PlanningConfig
    ) -> None:
        """The line is still planned, and the log names it.

        Notes:
            An exception would fail the whole run over one missing row, and
            inventing a requirement would strand work nobody could be
            qualified for.
        """
        built = _service(config).build(
            [_quote(None)],
            {"customer-1": _customer()},
            {},
            MONDAY,
            MONDAY,
        )

        assert built[0].required_skill_codes == []
