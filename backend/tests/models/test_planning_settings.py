from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from typing import Union

# Third-party imports
import pytest

# First-party imports
from models.settings.exceptions import (
    MTInvalidPlanningSettingsException,
    MTPlanningSettingsInvalidDate,
    MTPlanningSettingsInvalidId,
    MTPlanningSettingsInvalidLunchBreak,
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
