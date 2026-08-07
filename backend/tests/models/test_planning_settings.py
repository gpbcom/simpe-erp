from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime, time
from typing import Dict, Union

# Third-party imports
from pydantic import JsonValue
import pytest

# First-party imports
from models.settings.exceptions import (
    MTInvalidPlanningSettingsException,
    MTPlanningSettingsInvalidDate,
    MTPlanningSettingsInvalidDayEnd,
    MTPlanningSettingsInvalidDayStart,
    MTPlanningSettingsInvalidId,
    MTPlanningSettingsInvalidLunchBreak,
    MTPlanningSettingsInvalidLunchWindow,
    MTPlanningSettingsInvalidRadius,
    MTPlanningSettingsInvalidUpdatedBy,
)
from models.settings.planning_settings import PlanningSettings


class TestPlanningSettings:
    """Tests for the planning rules a manager owns."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_a_radius_alone_is_enough(self) -> None:
        """The lunch break defaults to the contractual hour."""
        settings = PlanningSettings(max_intervention_radius_km=30)

        assert settings.max_intervention_radius_km == 30.0
        assert settings.lunch_break_minutes == 60

    def test_the_identifier_defaults_to_the_singleton(self) -> None:
        """A caller never has to know the magic identifier."""
        assert PlanningSettings(max_intervention_radius_km=30).id == (
            PlanningSettings.SINGLETON_ID
        )

    # ------------------------------------------------------------------ #
    #  id validation
    # ------------------------------------------------------------------ #

    def test_the_singleton_identifier_is_accepted(self) -> None:
        """Reading the stored row back works."""
        settings = PlanningSettings(
            id=PlanningSettings.SINGLETON_ID, max_intervention_radius_km=30
        )

        assert settings.id == PlanningSettings.SINGLETON_ID

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("other-settings", id="Invalid - a second row"),
            pytest.param("", id="Invalid - empty"),
            pytest.param(7, id="Invalid - not a string"),
        ],
    )
    def test_any_other_identifier_is_refused(self, value: Union[str, int]) -> None:
        """There is nowhere for a second set of rules to live.

        Args:
            value (Union[str, int]): The rejected identifier.

        Notes:
            Refusing here is what keeps the table to one row even if a caller
            invents an identifier — and a second row would raise the question
            of which one the solver read, whose answer would be insertion
            order.
        """
        with pytest.raises(MTPlanningSettingsInvalidId):
            PlanningSettings(id=value, max_intervention_radius_km=30)

    # ------------------------------------------------------------------ #
    #  radius validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(0.1, id="Valid - the floor"),
            pytest.param(30, id="Valid - an integer"),
            pytest.param("45.5", id="Valid - a numeric string"),
            pytest.param(500.0, id="Valid - the ceiling"),
        ],
    )
    def test_a_usable_radius_is_accepted(self, value: Union[float, int, str]) -> None:
        """Anything a manager would reasonably type is accepted.

        Args:
            value (Union[float, int, str]): The radius to check.
        """
        assert PlanningSettings(max_intervention_radius_km=value)

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(-5, id="Invalid - negative"),
            pytest.param(1000, id="Invalid - past the ceiling"),
            pytest.param("wide", id="Invalid - not a number"),
            pytest.param(None, id="Invalid - missing"),
        ],
    )
    def test_an_unusable_radius_is_refused(
        self, value: Union[float, int, str, None]
    ) -> None:
        """Both ends are bounded, and for opposite reasons.

        Args:
            value (Union[float, int, str, None]): The rejected radius.

        Notes:
            Zero would place nothing at all and read as a broken planner; an
            unbounded value would silently switch the constraint off, which is
            the failure that looks like success.
        """
        with pytest.raises(MTPlanningSettingsInvalidRadius):
            PlanningSettings(max_intervention_radius_km=value)

    # ------------------------------------------------------------------ #
    #  lunch break validation
    # ------------------------------------------------------------------ #

    def test_a_longer_break_is_accepted(self) -> None:
        """A manager may be more generous than the floor."""
        assert (
            PlanningSettings(
                max_intervention_radius_km=30, lunch_break_minutes=90
            ).lunch_break_minutes
            == 90
        )

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(30, id="Invalid - below the floor"),
            pytest.param(0, id="Invalid - none at all"),
            pytest.param(-60, id="Invalid - negative"),
            pytest.param(True, id="Invalid - a boolean"),
            pytest.param("an hour", id="Invalid - not a number"),
        ],
    )
    def test_a_break_below_the_floor_is_refused(
        self, value: Union[int, bool, str]
    ) -> None:
        """The contractual hour cannot be shortened by configuration.

        Args:
            value (Union[int, bool, str]): The rejected break length.

        Notes:
            A break under an hour is not a preference; it is a plan that
            breaches the agreement it was built from, and enforcing it here
            means no screen has to remember to.
        """
        with pytest.raises(MTPlanningSettingsInvalidLunchBreak):
            PlanningSettings(max_intervention_radius_km=30, lunch_break_minutes=value)

    # ------------------------------------------------------------------ #
    #  Audit fields
    # ------------------------------------------------------------------ #

    def test_seeded_settings_have_no_editor(self) -> None:
        """Nobody decided the defaults, so nobody is recorded."""
        assert PlanningSettings(max_intervention_radius_km=30).updated_by is None

    def test_an_empty_editor_is_refused(self) -> None:
        """A blank name is worse than none: it looks like a record."""
        with pytest.raises(MTPlanningSettingsInvalidUpdatedBy):
            PlanningSettings(max_intervention_radius_km=30, updated_by="  ")

    def test_a_bad_timestamp_is_refused(self) -> None:
        """A malformed change time is refused rather than dropped."""
        with pytest.raises(MTPlanningSettingsInvalidDate):
            PlanningSettings(max_intervention_radius_km=30, updated_at="yesterday")

    # ------------------------------------------------------------------ #
    #  covers()
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        ("distance", "expected"),
        [
            pytest.param(0.0, True, id="At home"),
            pytest.param(29.9, True, id="Inside"),
            pytest.param(30.0, True, id="Exactly at the limit"),
            pytest.param(30.1, False, id="Just outside"),
            pytest.param(130.0, False, id="Far outside"),
        ],
    )
    def test_the_boundary_is_inclusive(self, distance: float, expected: bool) -> None:
        """A visit exactly at the limit is inside it.

        Args:
            distance (float): The distance to check.
            expected (bool): Whether it should be covered.

        Notes:
            Excluding the boundary would make a round-numbered radius behave
            one metre tighter than the number an administrator typed, which is
            the kind of discrepancy nobody finds by reading the code.
        """
        settings = PlanningSettings(max_intervention_radius_km=30.0)

        assert settings.covers(distance) is expected

    # ------------------------------------------------------------------ #
    #  Working day and lunch window
    # ------------------------------------------------------------------ #

    def test_the_working_day_defaults_to_nine_to_eight(self) -> None:
        """A caller who names only a radius gets the shipped working day."""
        settings = PlanningSettings(max_intervention_radius_km=30)

        assert settings.day_start_minute == 9 * 60
        assert settings.day_end_minute == 20 * 60
        assert settings.lunch_window_start_minute == 11 * 60 + 30
        assert settings.lunch_window_end_minute == 14 * 60 + 30

    def test_the_working_day_is_configurable(self) -> None:
        """A manager may move the day, which is the point of storing it.

        Notes:
            The whole feature is this assertion: before these fields existed
            the day came from ``app.yaml`` and moving it needed a deployment.
        """
        settings = PlanningSettings(
            max_intervention_radius_km=30,
            day_start_minute=8 * 60,
            day_end_minute=19 * 60 + 30,
            lunch_window_start_minute=12 * 60,
            lunch_window_end_minute=13 * 60 + 30,
        )

        assert settings.day_start_time() == time(8, 0)
        assert settings.day_end_time() == time(19, 30)
        assert settings.describe_working_day() == "08:00–19:30"

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param(True, id="Invalid - a bool masquerading as an int"),
            pytest.param("morning", id="Invalid - not a number"),
            pytest.param(-1, id="Invalid - before midnight"),
            pytest.param(24 * 60 + 1, id="Invalid - past the end of the day"),
        ],
    )
    def test_a_minute_outside_the_day_is_refused(self, value: JsonValue) -> None:
        """A minute of day must actually name a minute of the day.

        Args:
            value (JsonValue): The rejected minute.

        Notes:
            ``True`` is included deliberately. It is an ``int`` in Python, and
            a validator that only checked the range would store it as one
            minute past midnight.
        """
        with pytest.raises(MTPlanningSettingsInvalidDayStart):
            PlanningSettings(max_intervention_radius_km=30, day_start_minute=value)

    def test_a_day_that_ends_before_it_starts_is_refused(self) -> None:
        """Two individually valid minutes can still be a day nobody works."""
        with pytest.raises(MTPlanningSettingsInvalidDayEnd):
            PlanningSettings(
                max_intervention_radius_km=30,
                day_start_minute=20 * 60,
                day_end_minute=9 * 60,
            )

    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param(
                {
                    "lunch_window_start_minute": 14 * 60,
                    "lunch_window_end_minute": 12 * 60,
                },
                id="Invalid - the window ends before it starts",
            ),
            pytest.param(
                {
                    "day_start_minute": 10 * 60,
                    "lunch_window_start_minute": 9 * 60,
                    "lunch_window_end_minute": 12 * 60,
                },
                id="Invalid - lunch starts before the day does",
            ),
            pytest.param(
                {
                    "day_end_minute": 13 * 60,
                    "lunch_window_start_minute": 11 * 60 + 30,
                    "lunch_window_end_minute": 14 * 60,
                },
                id="Invalid - lunch ends after the day does",
            ),
            pytest.param(
                {
                    "lunch_break_minutes": 120,
                    "lunch_window_start_minute": 12 * 60,
                    "lunch_window_end_minute": 13 * 60,
                },
                id="Invalid - the window cannot hold the break",
            ),
        ],
    )
    def test_an_unworkable_lunch_window_is_refused(
        self, overrides: Dict[str, int]
    ) -> None:
        """The window has to sit inside the day and hold the break.

        Args:
            overrides (Dict[str, int]): The fields making it unworkable.

        Notes:
            Every one of these is a pair of values that are individually
            plausible. Caught here it is a 422 naming the conflict; caught by
            the solver it is a planning run that fails against every visit with
            "no feasible slot", which names nothing.
        """
        with pytest.raises(MTPlanningSettingsInvalidLunchWindow):
            PlanningSettings(max_intervention_radius_km=30, **overrides)

    def test_a_lunch_window_exactly_as_wide_as_the_break_is_accepted(self) -> None:
        """The width check is inclusive; a break that just fits, fits."""
        settings = PlanningSettings(
            max_intervention_radius_km=30,
            lunch_break_minutes=60,
            lunch_window_start_minute=12 * 60,
            lunch_window_end_minute=13 * 60,
        )

        assert settings.lunch_window_end_minute == 13 * 60

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception",
        [
            pytest.param(MTPlanningSettingsInvalidId, id="id"),
            pytest.param(MTPlanningSettingsInvalidRadius, id="radius"),
            pytest.param(MTPlanningSettingsInvalidLunchBreak, id="lunch break"),
            pytest.param(MTPlanningSettingsInvalidUpdatedBy, id="updated by"),
            pytest.param(MTPlanningSettingsInvalidDate, id="date"),
            pytest.param(MTPlanningSettingsInvalidDayStart, id="day start"),
            pytest.param(MTPlanningSettingsInvalidDayEnd, id="day end"),
            pytest.param(MTPlanningSettingsInvalidLunchWindow, id="lunch window"),
        ],
    )
    def test_every_leaf_shares_one_base(self, exception: type) -> None:
        """One except clause catches everything this model raises.

        Args:
            exception (type): The leaf exception to check.
        """
        assert issubclass(exception, MTInvalidPlanningSettingsException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_it_round_trips(self) -> None:
        """Dumped settings rebuild identically."""
        settings = PlanningSettings(
            max_intervention_radius_km=45.5,
            lunch_break_minutes=90,
            updated_by="user-1",
            updated_at=datetime.now(UTC),
        )
        rebuilt = PlanningSettings.model_validate(settings.model_dump())

        assert rebuilt.max_intervention_radius_km == 45.5
        assert rebuilt.lunch_break_minutes == 90
        assert rebuilt.updated_by == "user-1"
