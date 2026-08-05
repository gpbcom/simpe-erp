from __future__ import annotations

# Standard library imports
from decimal import Decimal
from enum import StrEnum
from typing import Any

# Third-party imports
import pytest

from models.enums import (
    AvailabilityKind,
    ContractType,
    InterventionStatus,
    PlanningRunStatus,
    QuoteStatus,
    RegistrationStatus,
    ServiceCategory,
    UserRole,
    Weekday,
)

# First-party imports
from models.exceptions.enum_exceptions import MTInvalidWeekday

ALL_ENUMS = (
    AvailabilityKind,
    ContractType,
    InterventionStatus,
    PlanningRunStatus,
    QuoteStatus,
    RegistrationStatus,
    ServiceCategory,
    UserRole,
    Weekday,
)


class TestEnums:
    """Tests for the shared enumerations."""

    # ------------------------------------------------------------------ #
    #  Shape
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("enum_class", ALL_ENUMS)
    def test_every_enum_is_a_str_enum(self, enum_class: type) -> None:
        """Every enum subclasses StrEnum so it serialises as its value."""
        assert issubclass(enum_class, StrEnum)

    @pytest.mark.parametrize("enum_class", ALL_ENUMS)
    def test_every_enum_has_unique_values(self, enum_class: type) -> None:
        """@unique forbids two members sharing one value."""
        values = [member.value for member in enum_class]
        assert len(values) == len(set(values))

    @pytest.mark.parametrize("enum_class", ALL_ENUMS)
    def test_values_helper_matches_the_members(self, enum_class: Any) -> None:
        """``values()`` returns every member value, in declaration order."""
        assert enum_class.values() == tuple(member.value for member in enum_class)

    @pytest.mark.parametrize("enum_class", ALL_ENUMS)
    def test_members_are_upper_snake_case(self, enum_class: type) -> None:
        """Member names are UPPER_SNAKE, as the house style requires."""
        for member in enum_class:
            assert member.name == member.name.upper()

    # ------------------------------------------------------------------ #
    #  ServiceCategory
    # ------------------------------------------------------------------ #

    def test_necessity_is_taxed_at_the_reduced_rate(self) -> None:
        """A necessity service carries the reduced 5.5% VAT rate."""
        assert ServiceCategory.NECESSITY.vat_rate() == Decimal("0.055")

    def test_comfort_is_taxed_at_the_standard_rate(self) -> None:
        """A comfort service carries the standard 20% VAT rate."""
        assert ServiceCategory.COMFORT.vat_rate() == Decimal("0.20")

    @pytest.mark.parametrize("category", list(ServiceCategory))
    def test_vat_rate_is_a_decimal(self, category: ServiceCategory) -> None:
        """VAT rates are Decimal, never float, so pricing never loses cents."""
        assert isinstance(category.vat_rate(), Decimal)

    # ------------------------------------------------------------------ #
    #  UserRole
    # ------------------------------------------------------------------ #

    def test_roles_rank_hca_below_manager_below_admin(self) -> None:
        """The role ranking is strictly increasing in privilege."""
        assert UserRole.HCA.rank() < UserRole.MANAGER.rank() < UserRole.ADMIN.rank()

    @pytest.mark.parametrize(
        ("role", "minimum", "expected"),
        [
            pytest.param(UserRole.ADMIN, UserRole.MANAGER, True, id="admin >= manager"),
            pytest.param(
                UserRole.MANAGER, UserRole.MANAGER, True, id="manager = manager"
            ),
            pytest.param(UserRole.HCA, UserRole.MANAGER, False, id="hca < manager"),
            pytest.param(UserRole.ADMIN, UserRole.ADMIN, True, id="admin = admin"),
            pytest.param(UserRole.MANAGER, UserRole.ADMIN, False, id="manager < admin"),
        ],
    )
    def test_has_at_least(
        self, role: UserRole, minimum: UserRole, expected: bool
    ) -> None:
        """``has_at_least`` compares roles by rank."""
        assert role.has_at_least(minimum) is expected

    def test_every_role_has_a_rank(self) -> None:
        """No role is missing from the rank table."""
        assert {role.rank() for role in UserRole} == {0, 1, 2}

    # ------------------------------------------------------------------ #
    #  Weekday
    # ------------------------------------------------------------------ #

    def test_iso_weekday_numbers_monday_first(self) -> None:
        """ISO weekday numbering runs Monday=1 through Sunday=7."""
        assert Weekday.MONDAY.iso_weekday() == 1
        assert Weekday.SUNDAY.iso_weekday() == 7

    @pytest.mark.parametrize("day", list(Weekday))
    def test_from_iso_weekday_round_trips(self, day: Weekday) -> None:
        """Converting to an ISO number and back yields the same weekday."""
        assert Weekday.from_iso_weekday(day.iso_weekday()) is day

    @pytest.mark.parametrize(
        "invalid_number",
        [
            pytest.param(0, id="Invalid - below range"),
            pytest.param(8, id="Invalid - above range"),
            pytest.param(-1, id="Invalid - negative"),
            pytest.param("1", id="Invalid - string"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_from_iso_weekday_rejects_out_of_range(self, invalid_number: Any) -> None:
        """An ISO weekday outside 1..7 is rejected.

        Notes:
            The enumeration raises its own exception rather than ``ValueError``,
            so the API's handler can map it like every other domain failure.
        """
        with pytest.raises(MTInvalidWeekday):
            Weekday.from_iso_weekday(invalid_number)

    def test_from_iso_weekday_agrees_with_the_calendar(self) -> None:
        """The mapping matches date.isoweekday for a known date."""
        # Standard library imports
        from datetime import date

        # 9 August 2026 is a Sunday.
        assert Weekday.from_iso_weekday(date(2026, 8, 9).isoweekday()) is Weekday.SUNDAY

    # ------------------------------------------------------------------ #
    #  PlanningRunStatus
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            pytest.param(
                PlanningRunStatus.PENDING, False, id="pending is not terminal"
            ),
            pytest.param(
                PlanningRunStatus.RUNNING, False, id="running is not terminal"
            ),
            pytest.param(PlanningRunStatus.SUCCEEDED, True, id="succeeded is terminal"),
            pytest.param(PlanningRunStatus.FAILED, True, id="failed is terminal"),
        ],
    )
    def test_is_terminal(self, status: PlanningRunStatus, expected: bool) -> None:
        """Only succeeded and failed end a run; clients poll until then."""
        assert status.is_terminal() is expected

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("enum_class", ALL_ENUMS)
    def test_members_compare_equal_to_their_string_value(
        self, enum_class: type
    ) -> None:
        """A StrEnum member equals its own value, which is what JSON carries."""
        for member in enum_class:
            assert member == member.value

    def test_contract_types_cover_the_four_french_contracts(self) -> None:
        """The contract catalog is exactly CDI, CDD, interim and internship."""
        assert set(ContractType.values()) == {"cdi", "cdd", "interim", "internship"}

    def test_registration_statuses_are_active_and_stopped(self) -> None:
        """A customer is either active or stopped."""
        assert set(RegistrationStatus.values()) == {"active", "stopped"}

    def test_quote_statuses_include_accepted(self) -> None:
        """Accepted is the status the planning computation selects on."""
        assert QuoteStatus.ACCEPTED in set(QuoteStatus)

    def test_availability_kinds_all_block_scheduling(self) -> None:
        """Every availability kind is a reason the assistant cannot work."""
        assert set(AvailabilityKind.values()) == {
            "holiday",
            "day-off",
            "sick-leave",
            "training",
            "unavailable",
        }

    def test_intervention_statuses_include_planned(self) -> None:
        """Planned is the status the solver writes."""
        assert InterventionStatus.PLANNED in set(InterventionStatus)
