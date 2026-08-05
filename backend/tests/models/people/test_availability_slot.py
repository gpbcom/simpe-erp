from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import Any, Dict

# Third-party imports
import pytest

# First-party imports
from models.enums import AvailabilityKind
from models.people.availability_slot import AvailabilitySlot
from models.people.exceptions import (
    MTAvailabilitySlotInvalidEndDate,
    MTAvailabilitySlotInvalidEndTime,
    MTAvailabilitySlotInvalidHcaId,
    MTAvailabilitySlotInvalidId,
    MTAvailabilitySlotInvalidKind,
    MTAvailabilitySlotInvalidNote,
    MTAvailabilitySlotInvalidStartDate,
    MTAvailabilitySlotInvalidStartTime,
    MTInvalidAvailabilitySlotException,
)


@pytest.fixture
def valid_slot_kwargs() -> Dict[str, Any]:
    """Return the keyword arguments for a week of annual leave.

    Returns:
        Dict[str, Any]: Constructor keyword arguments.
    """
    return {
        "hca_id": "hca-1",
        "start_date": date(2026, 8, 10),
        "end_date": date(2026, 8, 14),
        "kind": AvailabilityKind.HOLIDAY,
    }


class TestAvailabilitySlot:
    """Tests for the AvailabilitySlot model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_minimal_valid_construction(
        self, valid_slot_kwargs: Dict[str, Any]
    ) -> None:
        """A slot is a period, an assistant and a reason."""
        slot = AvailabilitySlot(**valid_slot_kwargs)
        assert slot.hca_id == "hca-1"
        assert slot.kind is AvailabilityKind.HOLIDAY
        assert slot.id is None

    def test_a_single_day_slot(self, valid_slot_kwargs: Dict[str, Any]) -> None:
        """One day off is a slot whose start and end are the same date.

        Notes:
            The range is inclusive, so a single day is not a zero-width range.
        """
        slot = AvailabilitySlot(
            **{
                **valid_slot_kwargs,
                "start_date": date(2026, 8, 10),
                "end_date": date(2026, 8, 10),
            }
        )
        assert slot.covers(date(2026, 8, 10)) is True

    def test_iso_strings_are_parsed(self, valid_slot_kwargs: Dict[str, Any]) -> None:
        """Dates and times may be supplied as ISO-8601 strings."""
        slot = AvailabilitySlot(
            **{
                **valid_slot_kwargs,
                "start_date": "2026-08-10",
                "end_date": "2026-08-14",
                "start_time": "09:00",
                "end_time": "12:00",
            }
        )
        assert slot.start_date == date(2026, 8, 10)
        assert slot.start_time == time(9, 0)

    def test_kind_is_coerced_from_a_string(
        self, valid_slot_kwargs: Dict[str, Any]
    ) -> None:
        """A string kind becomes an AvailabilityKind member."""
        slot = AvailabilitySlot(**{**valid_slot_kwargs, "kind": "sick-leave"})
        assert slot.kind is AvailabilityKind.SICK_LEAVE

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_id",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_invalid_id_raises(
        self, valid_slot_kwargs: Dict[str, Any], invalid_id: Any
    ) -> None:
        """An id that is neither None nor a non-empty string is rejected."""
        with pytest.raises(MTAvailabilitySlotInvalidId):
            AvailabilitySlot(**{**valid_slot_kwargs, "id": invalid_id})

    @pytest.mark.parametrize(
        "invalid_hca_id",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(1, id="Invalid - int"),
        ],
    )
    def test_invalid_hca_id_raises(
        self, valid_slot_kwargs: Dict[str, Any], invalid_hca_id: Any
    ) -> None:
        """A slot must name the assistant it belongs to."""
        with pytest.raises(MTAvailabilitySlotInvalidHcaId):
            AvailabilitySlot(**{**valid_slot_kwargs, "hca_id": invalid_hca_id})

    def test_invalid_start_date_raises(self, valid_slot_kwargs: Dict[str, Any]) -> None:
        """A non date-like start_date is rejected."""
        with pytest.raises(MTAvailabilitySlotInvalidStartDate):
            AvailabilitySlot(**{**valid_slot_kwargs, "start_date": 20260810})

    def test_invalid_end_date_raises(self, valid_slot_kwargs: Dict[str, Any]) -> None:
        """A non date-like end_date is rejected."""
        with pytest.raises(MTAvailabilitySlotInvalidEndDate):
            AvailabilitySlot(**{**valid_slot_kwargs, "end_date": ["2026", "08"]})

    @pytest.mark.parametrize(
        "invalid_kind",
        [
            pytest.param("vacation", id="Invalid - unknown kind"),
            pytest.param("HOLIDAY", id="Invalid - wrong case"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_invalid_kind_raises(
        self, valid_slot_kwargs: Dict[str, Any], invalid_kind: Any
    ) -> None:
        """A kind outside the enum is rejected, naming the valid set."""
        with pytest.raises(MTAvailabilitySlotInvalidKind):
            AvailabilitySlot(**{**valid_slot_kwargs, "kind": invalid_kind})

    def test_invalid_start_time_raises(self, valid_slot_kwargs: Dict[str, Any]) -> None:
        """A non time-like start_time is rejected."""
        with pytest.raises(MTAvailabilitySlotInvalidStartTime):
            AvailabilitySlot(**{**valid_slot_kwargs, "start_time": 900})

    def test_invalid_end_time_raises(self, valid_slot_kwargs: Dict[str, Any]) -> None:
        """A non time-like end_time is rejected."""
        with pytest.raises(MTAvailabilitySlotInvalidEndTime):
            AvailabilitySlot(**{**valid_slot_kwargs, "end_time": 1200})

    def test_a_blank_note_becomes_none(self, valid_slot_kwargs: Dict[str, Any]) -> None:
        """A whitespace-only note is stored as absent."""
        slot = AvailabilitySlot(**{**valid_slot_kwargs, "note": "   "})
        assert slot.note is None

    def test_invalid_note_raises(self, valid_slot_kwargs: Dict[str, Any]) -> None:
        """A non-string note is rejected."""
        with pytest.raises(MTAvailabilitySlotInvalidNote):
            AvailabilitySlot(**{**valid_slot_kwargs, "note": 42})

    # ------------------------------------------------------------------ #
    #  Cross-field validation
    # ------------------------------------------------------------------ #

    def test_an_end_before_the_start_raises(
        self, valid_slot_kwargs: Dict[str, Any]
    ) -> None:
        """The period cannot run backwards."""
        with pytest.raises(MTAvailabilitySlotInvalidEndDate):
            AvailabilitySlot(
                **{
                    **valid_slot_kwargs,
                    "start_date": date(2026, 8, 14),
                    "end_date": date(2026, 8, 10),
                }
            )

    @pytest.mark.parametrize(
        ("start_time", "end_time"),
        [
            pytest.param(time(9, 0), None, id="start only"),
            pytest.param(None, time(12, 0), id="end only"),
        ],
    )
    def test_a_half_set_time_window_raises(
        self, valid_slot_kwargs: Dict[str, Any], start_time: Any, end_time: Any
    ) -> None:
        """Both times are set or neither is.

        Notes:
            A half-open window would be ambiguous about which side of the day
            is blocked, and ``is_whole_day`` relies on the invariant.
        """
        with pytest.raises(MTAvailabilitySlotInvalidEndTime):
            AvailabilitySlot(
                **{
                    **valid_slot_kwargs,
                    "start_time": start_time,
                    "end_time": end_time,
                }
            )

    @pytest.mark.parametrize(
        ("start_time", "end_time"),
        [
            pytest.param(time(12, 0), time(9, 0), id="inverted"),
            pytest.param(time(12, 0), time(12, 0), id="zero width"),
        ],
    )
    def test_an_invalid_time_window_raises(
        self, valid_slot_kwargs: Dict[str, Any], start_time: time, end_time: time
    ) -> None:
        """The blocked window must have a positive width."""
        with pytest.raises(MTAvailabilitySlotInvalidEndTime):
            AvailabilitySlot(
                **{
                    **valid_slot_kwargs,
                    "start_time": start_time,
                    "end_time": end_time,
                }
            )

    # ------------------------------------------------------------------ #
    #  is_whole_day / covers
    # ------------------------------------------------------------------ #

    def test_a_slot_without_times_is_a_whole_day(
        self, valid_slot_kwargs: Dict[str, Any]
    ) -> None:
        """No time window means the whole day is blocked."""
        assert AvailabilitySlot(**valid_slot_kwargs).is_whole_day() is True

    def test_a_slot_with_times_is_partial(
        self, valid_slot_kwargs: Dict[str, Any]
    ) -> None:
        """A time window carves out part of the day only."""
        slot = AvailabilitySlot(
            **{**valid_slot_kwargs, "start_time": time(9, 0), "end_time": time(12, 0)}
        )
        assert slot.is_whole_day() is False

    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            pytest.param(date(2026, 8, 10), True, id="first day"),
            pytest.param(date(2026, 8, 12), True, id="middle day"),
            pytest.param(date(2026, 8, 14), True, id="last day, inclusive"),
            pytest.param(date(2026, 8, 9), False, id="day before"),
            pytest.param(date(2026, 8, 15), False, id="day after"),
        ],
    )
    def test_covers(
        self, valid_slot_kwargs: Dict[str, Any], day: date, expected: bool
    ) -> None:
        """The range is inclusive at both ends."""
        assert AvailabilitySlot(**valid_slot_kwargs).covers(day) is expected

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTAvailabilitySlotInvalidEndDate,
            MTAvailabilitySlotInvalidEndTime,
            MTAvailabilitySlotInvalidHcaId,
            MTAvailabilitySlotInvalidId,
            MTAvailabilitySlotInvalidKind,
            MTAvailabilitySlotInvalidNote,
            MTAvailabilitySlotInvalidStartDate,
            MTAvailabilitySlotInvalidStartTime,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidAvailabilitySlotException."""
        assert issubclass(exception_class, MTInvalidAvailabilitySlotException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_model_dump_round_trip(self, valid_slot_kwargs: Dict[str, Any]) -> None:
        """A slot survives a dump-and-rebuild unchanged."""
        slot = AvailabilitySlot(
            **{**valid_slot_kwargs, "start_time": time(9, 0), "end_time": time(12, 0)}
        )
        assert AvailabilitySlot(**slot.model_dump()) == slot
