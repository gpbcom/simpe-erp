from __future__ import annotations

# Standard library imports
from typing import Dict

# Third-party imports
from pydantic import JsonValue
import pytest

# First-party imports
from models.schemas.exceptions import (
    MTInvalidPlanningSettingsRequestException,
    MTPlanningSettingsRequestInvalidDayEnd,
    MTPlanningSettingsRequestInvalidDayStart,
    MTPlanningSettingsRequestInvalidLunchBreak,
    MTPlanningSettingsRequestInvalidLunchWindow,
    MTPlanningSettingsRequestInvalidRadius,
)
from models.schemas.requests.planning.planning_settings_request import (
    PlanningSettingsRequest,
)
from models.settings.planning_settings import PlanningSettings


class TestPlanningSettingsRequest:
    """Tests for the payload a manager changes the planning rules with."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_a_radius_alone_is_enough(self) -> None:
        """A manager adjusting one rule need not restate the other five.

        Notes:
            This is why every field but the radius carries a default. A payload
            that omitted the working day would otherwise be rejected for a
            value the caller never intended to touch.
        """
        request = PlanningSettingsRequest(max_intervention_radius_km=30)

        assert request.day_start_minute == 9 * 60
        assert request.day_end_minute == 20 * 60
        assert request.lunch_break_minutes == 60
        assert request.lunch_window_start_minute == 11 * 60 + 30
        assert request.lunch_window_end_minute == 14 * 60 + 30

    def test_the_defaults_match_the_stored_model(self) -> None:
        """Two defaults that disagreed would move the day on a partial save.

        Notes:
            The payload's defaults and the stored model's are written out
            separately, so nothing but this test stops them drifting — and the
            drift would be silent: a manager changing only the radius would
            find the working day had moved too.
        """
        payload = PlanningSettingsRequest(max_intervention_radius_km=30)
        stored = PlanningSettings(max_intervention_radius_km=30)

        assert payload.day_start_minute == stored.day_start_minute
        assert payload.day_end_minute == stored.day_end_minute
        assert payload.lunch_break_minutes == stored.lunch_break_minutes
        assert payload.lunch_window_start_minute == stored.lunch_window_start_minute
        assert payload.lunch_window_end_minute == stored.lunch_window_end_minute

    def test_a_complete_payload_is_accepted(self) -> None:
        """The ordinary case: a manager moves the whole day."""
        request = PlanningSettingsRequest(
            max_intervention_radius_km=45,
            day_start_minute=8 * 60,
            day_end_minute=19 * 60,
            lunch_break_minutes=90,
            lunch_window_start_minute=12 * 60,
            lunch_window_end_minute=14 * 60,
        )

        assert request.day_start_minute == 480
        assert request.lunch_break_minutes == 90

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

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
        """
        with pytest.raises(MTPlanningSettingsRequestInvalidDayStart):
            PlanningSettingsRequest(
                max_intervention_radius_km=30, day_start_minute=value
            )

    def test_a_radius_outside_the_range_is_refused(self) -> None:
        """The outer gate answers before the stored model has to."""
        with pytest.raises(MTPlanningSettingsRequestInvalidRadius):
            PlanningSettingsRequest(max_intervention_radius_km=0)

    def test_a_break_below_the_floor_is_refused(self) -> None:
        """The contractual hour is enforced on the way in."""
        with pytest.raises(MTPlanningSettingsRequestInvalidLunchBreak):
            PlanningSettingsRequest(
                max_intervention_radius_km=30, lunch_break_minutes=30
            )

    # ------------------------------------------------------------------ #
    #  Cross-field validation
    # ------------------------------------------------------------------ #

    def test_a_day_that_ends_before_it_starts_is_refused(self) -> None:
        """Two individually valid minutes can still be a day nobody works."""
        with pytest.raises(MTPlanningSettingsRequestInvalidDayEnd):
            PlanningSettingsRequest(
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
        """The conflict is named as a 422 rather than left to the solver.

        Args:
            overrides (Dict[str, int]): The fields making it unworkable.

        Notes:
            Reaching the solver, the same payload produces a planning run that
            fails against every visit with "no feasible slot" — which names
            nothing a manager can act on.
        """
        with pytest.raises(MTPlanningSettingsRequestInvalidLunchWindow):
            PlanningSettingsRequest(max_intervention_radius_km=30, **overrides)

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception",
        [
            pytest.param(MTPlanningSettingsRequestInvalidRadius, id="radius"),
            pytest.param(MTPlanningSettingsRequestInvalidLunchBreak, id="lunch break"),
            pytest.param(MTPlanningSettingsRequestInvalidDayStart, id="day start"),
            pytest.param(MTPlanningSettingsRequestInvalidDayEnd, id="day end"),
            pytest.param(
                MTPlanningSettingsRequestInvalidLunchWindow, id="lunch window"
            ),
        ],
    )
    def test_every_leaf_shares_one_base(self, exception: type) -> None:
        """One handler row answers every rejection with a 422.

        Args:
            exception (type): The leaf exception to check.
        """
        assert issubclass(exception, MTInvalidPlanningSettingsRequestException)
