from __future__ import annotations

# Standard library imports
from datetime import time

# Third-party imports
import pytest

# First-party imports
from models.configuration.exceptions import (
    MTInvalidPlanningConfigException,
    MTPlanningConfigInvalidDayEnd,
    MTPlanningConfigInvalidDayStart,
    MTPlanningConfigInvalidLunchBreak,
    MTPlanningConfigInvalidLunchWindow,
    MTPlanningConfigInvalidPenalty,
    MTPlanningConfigInvalidSolverTimeLimit,
    MTPlanningConfigInvalidSolverWorkers,
    MTPlanningConfigInvalidSpeed,
)
from models.configuration.planning_config import PlanningConfig
from tests.annotations import ModelInput


class TestPlanningConfig:
    """Tests for the PlanningConfig model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_defaults_match_the_business_rules(self) -> None:
        """The day runs 09:00-20:00 with a one-hour lunch break."""
        config = PlanningConfig()
        assert config.day_start_minute == 9 * 60
        assert config.day_end_minute == 20 * 60
        assert config.lunch_break_minutes == 60

    def test_default_lunch_window_straddles_midday(self) -> None:
        """The break may be taken between 11:30 and 14:30 by default."""
        config = PlanningConfig()
        assert config.lunch_window_start_minute == 11 * 60 + 30
        assert config.lunch_window_end_minute == 14 * 60 + 30

    def test_default_speeds_differ_by_licence(self) -> None:
        """A licensed assistant is assumed to travel faster."""
        config = PlanningConfig()
        assert config.average_speed_kmh > config.average_speed_without_license_kmh

    def test_unassigned_penalty_dominates_travel(self) -> None:
        """Leaving work unassigned must never be cheaper than a long drive.

        Notes:
            The solver is allowed to leave a requirement unassigned rather than
            fail. If the penalty did not dominate, it would do so routinely.
        """
        config = PlanningConfig()
        minutes_in_a_long_day = config.day_end_minute - config.day_start_minute
        assert config.unassigned_penalty > config.travel_weight * minutes_in_a_long_day

    # ------------------------------------------------------------------ #
    #  minute-of-day validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "field",
        [
            "day_start_minute",
            "day_end_minute",
            "lunch_window_start_minute",
            "lunch_window_end_minute",
        ],
    )
    @pytest.mark.parametrize(
        "invalid_minute",
        [
            pytest.param(-1, id="Invalid - negative"),
            pytest.param(1441, id="Invalid - beyond a day"),
            pytest.param("540", id="Invalid - string"),
            pytest.param(540.0, id="Invalid - float"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(True, id="Invalid - bool"),
        ],
    )
    def test_invalid_minute_of_day_raises(
        self, field: str, invalid_minute: ModelInput
    ) -> None:
        """A minute-of-day outside 0..1440, or not an integer, is rejected."""
        with pytest.raises(MTPlanningConfigInvalidDayStart):
            PlanningConfig(**{field: invalid_minute})

    # ------------------------------------------------------------------ #
    #  lunch_break_minutes validation
    # ------------------------------------------------------------------ #

    def test_the_lunch_break_is_configurable(self) -> None:
        """A longer break is accepted, as the requirement demands."""
        config = PlanningConfig(lunch_break_minutes=90)
        assert config.lunch_break_minutes == 90

    @pytest.mark.parametrize(
        "invalid_break",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(-30, id="Invalid - negative"),
            pytest.param(1441, id="Invalid - beyond a day"),
            pytest.param("60", id="Invalid - string"),
            pytest.param(60.0, id="Invalid - float"),
            pytest.param(True, id="Invalid - bool"),
        ],
    )
    def test_invalid_lunch_break_raises(self, invalid_break: ModelInput) -> None:
        """A non-positive or absurd lunch break is rejected."""
        with pytest.raises(MTPlanningConfigInvalidLunchBreak):
            PlanningConfig(lunch_break_minutes=invalid_break)

    # ------------------------------------------------------------------ #
    #  speed validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "field", ["average_speed_kmh", "average_speed_without_license_kmh"]
    )
    @pytest.mark.parametrize(
        "invalid_speed",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(-10.0, id="Invalid - negative"),
            pytest.param("30", id="Invalid - string"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(True, id="Invalid - bool"),
        ],
    )
    def test_invalid_speed_raises(self, field: str, invalid_speed: ModelInput) -> None:
        """A non-positive speed is rejected before it divides by zero."""
        with pytest.raises(MTPlanningConfigInvalidSpeed):
            PlanningConfig(**{field: invalid_speed})

    # ------------------------------------------------------------------ #
    #  solver_time_limit_seconds validation
    # ------------------------------------------------------------------ #

    def test_a_short_solver_budget_is_accepted(self) -> None:
        """Tests run the solver with a two-second budget."""
        assert (
            PlanningConfig(solver_time_limit_seconds=2.0).solver_time_limit_seconds
            == 2.0
        )

    @pytest.mark.parametrize(
        "invalid_limit",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(-1.0, id="Invalid - negative"),
            pytest.param("30", id="Invalid - string"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_invalid_solver_time_limit_raises(self, invalid_limit: ModelInput) -> None:
        """A non-positive solver budget is rejected."""
        with pytest.raises(MTPlanningConfigInvalidSolverTimeLimit):
            PlanningConfig(solver_time_limit_seconds=invalid_limit)

    # ------------------------------------------------------------------ #
    #  solver_workers validation
    # ------------------------------------------------------------------ #

    def test_the_thread_count_is_configurable(self) -> None:
        """**A deployment can match it to the CPU it actually grants.**

        Notes:
            It was hard-coded at eight against a two-core container. The budget
            beside it is *wall-clock*, so under a container CPU limit the extra
            threads do not merely fail to help: the kernel throttles the whole
            cgroup, and a thirty-second budget takes a minute of real time while
            the run still reports as having used its budget.
        """
        assert PlanningConfig(solver_workers=2).solver_workers == 2

    def test_it_defaults_to_a_single_worker_for_reproducibility(self) -> None:
        """**The default is about the answer, not about the cores.**

        Notes:
            It was ``8``, chosen to preserve the behaviour that was hard-coded
            before the field existed. It is ``1`` now for a different reason
            entirely: CP-SAT's parallel workers race each other to the
            incumbent solution, so the plan depends on which one got there
            first. Re-planning an unchanged week returned 404 minutes of
            travel, then 371, then 355 — three numbers a manager cannot tell
            apart from a real improvement, and no way to see whether the quote
            they just accepted changed anything.

            Raising it trades that determinism back for speed, per
            deployment and on purpose.
        """
        assert PlanningConfig().solver_workers == 1

    @pytest.mark.parametrize(
        "invalid_workers",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(-1, id="Invalid - negative"),
            pytest.param(2.0, id="Invalid - float"),
            pytest.param("8", id="Invalid - string"),
            pytest.param(True, id="Invalid - bool"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_an_invalid_thread_count_raises(self, invalid_workers: ModelInput) -> None:
        """Zero is refused rather than read as "let the solver decide".

        Notes:
            CP-SAT takes zero as a request for no search at all: it returns
            immediately with UNKNOWN, and the run fails looking like an
            infeasible plan rather than like a misconfiguration.
        """
        with pytest.raises(MTPlanningConfigInvalidSolverWorkers):
            PlanningConfig(solver_workers=invalid_workers)

    # ------------------------------------------------------------------ #
    #  objective-term validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("field", ["travel_weight", "unassigned_penalty"])
    @pytest.mark.parametrize(
        "invalid_term",
        [
            pytest.param(-1, id="Invalid - negative"),
            pytest.param(1.5, id="Invalid - float"),
            pytest.param("10", id="Invalid - string"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_invalid_objective_term_raises(
        self, field: str, invalid_term: ModelInput
    ) -> None:
        """An objective weight must be a non-negative integer."""
        with pytest.raises(MTPlanningConfigInvalidPenalty):
            PlanningConfig(**{field: invalid_term})

    # ------------------------------------------------------------------ #
    #  Cross-field validation
    # ------------------------------------------------------------------ #

    def test_a_day_that_ends_before_it_starts_raises(self) -> None:
        """The working day must have a positive width."""
        with pytest.raises(MTPlanningConfigInvalidDayEnd):
            PlanningConfig(day_start_minute=20 * 60, day_end_minute=9 * 60)

    def test_a_zero_width_day_raises(self) -> None:
        """A day that starts and ends at the same minute is rejected."""
        with pytest.raises(MTPlanningConfigInvalidDayEnd):
            PlanningConfig(day_start_minute=9 * 60, day_end_minute=9 * 60)

    def test_an_inverted_lunch_window_raises(self) -> None:
        """The lunch window must have a positive width."""
        with pytest.raises(MTPlanningConfigInvalidLunchWindow):
            PlanningConfig(
                lunch_window_start_minute=14 * 60,
                lunch_window_end_minute=11 * 60,
            )

    def test_a_lunch_window_outside_the_day_raises(self) -> None:
        """The break cannot be scheduled before the day starts."""
        with pytest.raises(MTPlanningConfigInvalidLunchWindow):
            PlanningConfig(
                day_start_minute=9 * 60,
                day_end_minute=20 * 60,
                lunch_window_start_minute=8 * 60,
                lunch_window_end_minute=10 * 60,
            )

    def test_a_lunch_window_too_narrow_for_the_break_raises(self) -> None:
        """A 90-minute break will not fit in a 60-minute window.

        Notes:
            Caught here rather than surfacing as an unexplained infeasible
            solve, which is far harder to diagnose.
        """
        with pytest.raises(MTPlanningConfigInvalidLunchWindow):
            PlanningConfig(
                lunch_break_minutes=90,
                lunch_window_start_minute=12 * 60,
                lunch_window_end_minute=13 * 60,
            )

    def test_a_window_exactly_the_break_width_is_accepted(self) -> None:
        """A window exactly as wide as the break pins it to one slot."""
        config = PlanningConfig(
            lunch_break_minutes=60,
            lunch_window_start_minute=12 * 60,
            lunch_window_end_minute=13 * 60,
        )
        assert config.lunch_break_minutes == 60

    # ------------------------------------------------------------------ #
    #  Conversion helpers
    # ------------------------------------------------------------------ #

    def test_day_bounds_convert_to_wall_clock_times(self) -> None:
        """Minutes from midnight convert back for display."""
        config = PlanningConfig()
        assert config.day_start_time() == time(9, 0)
        assert config.day_end_time() == time(20, 0)

    def test_day_bounds_convert_a_half_hour(self) -> None:
        """A non-round minute converts correctly."""
        config = PlanningConfig(day_start_minute=8 * 60 + 30)
        assert config.day_start_time() == time(8, 30)

    def test_speed_for_selects_by_licence(self) -> None:
        """An assistant without a licence gets the slower speed."""
        config = PlanningConfig()
        assert config.speed(True) == config.average_speed_kmh
        assert config.speed(False) == config.average_speed_without_license_kmh

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTPlanningConfigInvalidDayEnd,
            MTPlanningConfigInvalidDayStart,
            MTPlanningConfigInvalidLunchBreak,
            MTPlanningConfigInvalidLunchWindow,
            MTPlanningConfigInvalidPenalty,
            MTPlanningConfigInvalidSolverTimeLimit,
            MTPlanningConfigInvalidSpeed,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidPlanningConfigException."""
        assert issubclass(exception_class, MTInvalidPlanningConfigException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_model_dump_round_trip(self) -> None:
        """A config survives a dump-and-rebuild unchanged."""
        config = PlanningConfig(lunch_break_minutes=75)
        assert PlanningConfig(**config.model_dump()) == config

    def test_minutes_per_day_is_not_a_field(self) -> None:
        """The ClassVar stays out of the serialised payload."""
        assert "MINUTES_PER_DAY" not in PlanningConfig().model_dump()
