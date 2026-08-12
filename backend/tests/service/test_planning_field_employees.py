from __future__ import annotations

# Standard library imports
from datetime import date
from typing import List
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.configuration.planning_config import PlanningConfig
from models.enums import ContractType, UserRole
from models.geo.geo_point import GeoPoint
from models.people.hca import Hca
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)
from models.settings.planning_settings import PlanningSettings
from service.planning.plannings import PlanningService

MONDAY = date(2026, 8, 3)
HOME = GeoPoint(latitude=48.8566, longitude=2.3522)
NEARBY = GeoPoint(latitude=48.8600, longitude=2.3550)


@pytest.fixture
def config() -> PlanningConfig:
    """Return a planning configuration with a short solver budget.

    Returns:
        PlanningConfig: A two-second budget.
    """
    return PlanningConfig(solver_time_limit_seconds=2.0)


def _hca(hca_id: str = "hca-1", field_employee: bool = True) -> Hca:
    """Build an assistant record whose home is already geocoded.

    Args:
        hca_id (str): The identifier to assign.
        field_employee (bool): Whether they may be placed on a planning.

    Returns:
        Hca: The record.
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
        field_employee=field_employee,
    )


def _account(role: UserRole, hca_id: str) -> User:
    """Build the sign-in account bound to a record.

    Args:
        role (UserRole): The role the account holds.
        hca_id (str): The assistant record it is bound to.

    Returns:
        User: The account.
    """
    return User(
        company_id="company-1",
        id=f"user-{hca_id}",
        email=f"{hca_id}@example.com",
        full_name="Luc Martin",
        role=role,
        hca_id=hca_id,
    )


def _requirement(requirement_id: str = "req-1") -> InterventionRequirement:
    """Build one ungated piece of work.

    Args:
        requirement_id (str): The identifier to assign.

    Returns:
        InterventionRequirement: The work.
    """
    return InterventionRequirement(
        id=requirement_id,
        quote_line_id=requirement_id,
        customer_id=f"customer-{requirement_id}",
        name="Soin",
        intervention_type_id="type-1",
        day=MONDAY,
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
        teams=AsyncMock(),
        config=config,
    )


def _place(config: PlanningConfig, workforce: List[Hca]) -> List[str]:
    """Solve one visit over a workforce and return who was given it.

    Args:
        config (PlanningConfig): The planning rules.
        workforce (List[Hca]): Every record the agency holds.

    Returns:
        List[str]: The identifiers of the people assigned work.
    """
    service = _service(config)
    schedulable = service._field_employees(workforce)
    requirements = [_requirement()]
    service.build_travel(schedulable, requirements)
    solution = service.solve(
        requirements,
        schedulable,
        PlanningSettings(max_intervention_radius_km=200.0),
    )
    return [assignment.hca_id for assignment in solution.assignments]


class TestTheFlagDecidesAndTheRoleDoesNot:
    """Tests that ``field_employee`` alone decides who the planner may use.

    Notes:
        **The planner never sees an account.** It is handed ``Hca`` records,
        and ``UserRole`` does not appear in the run at all — so "whatever their
        role" is a property of the design rather than a branch anybody wrote.
        These tests pin it, because the tempting shortcut when somebody asks
        "why is a manager on this round?" is to add a role check here, and that
        would silently withdraw every manager who genuinely covers rounds.
    """

    @pytest.mark.parametrize("role", [UserRole.HCA, UserRole.MANAGER, UserRole.ADMIN])
    def test_a_field_employee_is_planned_whatever_their_account_holds(
        self, config: PlanningConfig, role: UserRole
    ) -> None:
        """A manager who also covers rounds is an ordinary thing to be.

        Args:
            config (PlanningConfig): The planning rules.
            role (UserRole): The role on the account bound to the record.
        """
        record = _hca("hca-1", field_employee=True)
        account = _account(role, "hca-1")
        assert account.hca_id == record.id

        assert _place(config, [record]) == ["hca-1"]

    @pytest.mark.parametrize("role", [UserRole.HCA, UserRole.MANAGER, UserRole.ADMIN])
    def test_a_non_field_employee_is_left_out_whatever_their_account_holds(
        self, config: PlanningConfig, role: UserRole
    ) -> None:
        """The flag withdraws an administrator exactly as it withdraws anybody.

        Args:
            config (PlanningConfig): The planning rules.
            role (UserRole): The role on the account bound to the record.
        """
        record = _hca("hca-1", field_employee=False)
        account = _account(role, "hca-1")
        assert account.hca_id == record.id

        assert _place(config, [record]) == []

    def test_the_run_reads_no_role_at_all(self, config: PlanningConfig) -> None:
        """The filter takes records, and a record carries no role.

        Notes:
            Stated as a property rather than a scenario: there is no way to
            hand ``_field_employees`` a role, which is why no ordering of roles
            can change its answer.
        """
        assert "role" not in Hca.model_fields

        mixed = [_hca("hca-1", True), _hca("hca-2", False), _hca("hca-3", True)]
        kept = _service(config)._field_employees(mixed)

        assert [person.id for person in kept] == ["hca-1", "hca-3"]

    def test_switching_the_flag_on_changes_who_the_next_run_uses(
        self, config: PlanningConfig
    ) -> None:
        """**The end of the chain the manager's switch starts.**

        Notes:
            The same record, planned or not planned, decided by nothing but
            this field. That is what makes the dropped argument in
            ``set_employment`` a scheduling bug rather than a cosmetic one.
        """
        assert _place(config, [_hca("hca-1", field_employee=False)]) == []
        assert _place(config, [_hca("hca-1", field_employee=True)]) == ["hca-1"]
