from __future__ import annotations

# Standard library imports
from datetime import date

# Third-party imports
import pytest

# First-party imports
from models.planning.planning_run.exceptions import (
    MTSuggestedSlotInvalidAssistant,
    MTSuggestedSlotInvalidDay,
    MTSuggestedSlotInvalidMinute,
    MTSuggestedSlotInvalidWindow,
)
from models.planning.planning_run.suggested_slot import SuggestedSlot
from tests.annotations import ModelInput

MONDAY = date(2026, 8, 3)


class TestBuildingASuggestedSlot:
    """Tests for the offer an operator telephones a customer about."""

    def test_it_carries_a_time_and_somebody_to_do_it(self) -> None:
        """A time nobody is attached to cannot be agreed with anybody."""
        slot = SuggestedSlot(
            day=MONDAY,
            start_minute=14 * 60,
            end_minute=15 * 60,
            hca_id="hca-1",
            hca_name="Amina Benali",
        )

        assert slot.day == MONDAY
        assert slot.hca_name == "Amina Benali"
        assert slot.duration_minutes() == 60

    def test_an_iso_day_is_accepted(self) -> None:
        """It arrives from JSON as a string when it is read back."""
        slot = SuggestedSlot(
            day="2026-08-03",
            start_minute=9 * 60,
            end_minute=10 * 60,
            hca_id="hca-1",
        )

        assert slot.day == MONDAY


class TestRefusingAnUnusableSlot:
    """Tests for offers nobody could act on."""

    @pytest.mark.parametrize("value", ["not-a-date", 42, None])
    def test_a_day_that_is_not_a_date_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected day.
        """
        with pytest.raises(MTSuggestedSlotInvalidDay):
            SuggestedSlot(day=value, start_minute=540, end_minute=600, hca_id="hca-1")

    @pytest.mark.parametrize("value", [-1, 24 * 60 + 1, "nine", True])
    def test_a_minute_outside_one_day_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected minute.
        """
        with pytest.raises(MTSuggestedSlotInvalidMinute):
            SuggestedSlot(
                day=MONDAY, start_minute=value, end_minute=600, hca_id="hca-1"
            )

    @pytest.mark.parametrize("end", [540, 500])
    def test_a_slot_that_does_not_run_forwards_is_refused(self, end: int) -> None:
        """A zero-length or reversed offer is not a time.

        Args:
            end (int): The rejected end minute.
        """
        with pytest.raises(MTSuggestedSlotInvalidWindow):
            SuggestedSlot(day=MONDAY, start_minute=540, end_minute=end, hca_id="hca-1")

    @pytest.mark.parametrize("value", ["", "   ", None, 7])
    def test_a_slot_with_nobody_attached_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected assistant identifier.
        """
        with pytest.raises(MTSuggestedSlotInvalidAssistant):
            SuggestedSlot(day=MONDAY, start_minute=540, end_minute=600, hca_id=value)


class TestStoringASuggestedSlot:
    """Tests that an offer survives the JSON column it lives in."""

    def test_it_serialises_and_reloads_unchanged(self) -> None:
        """It is written onto the quote and read back by the screen."""
        slot = SuggestedSlot(
            day=MONDAY,
            start_minute=14 * 60,
            end_minute=15 * 60,
            hca_id="hca-1",
            hca_name="Amina Benali",
        )

        restored = SuggestedSlot.model_validate(slot.model_dump(mode="json"))

        assert restored == slot

    def test_it_is_frozen(self) -> None:
        """An offer is a record of what was free, not a working value."""
        slot = SuggestedSlot(
            day=MONDAY, start_minute=540, end_minute=600, hca_id="hca-1"
        )

        with pytest.raises(Exception):
            slot.start_minute = 600
