from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Any

# Third-party imports
import pytest

# First-party imports
from models.schemas.exceptions import (
    MTInterventionRescheduleRequestInvalidDay,
    MTInterventionRescheduleRequestInvalidWindow,
    MTInvalidInterventionRescheduleRequestException,
)
from models.schemas.requests.customers.intervention_reschedule_request import (
    InterventionRescheduleRequest,
)

VALID = {"day": date(2026, 9, 14), "start_minute": 540, "end_minute": 720}


class TestInterventionRescheduleRequest:
    """Tests for when a household would rather a visit happened."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_a_day_and_a_window_are_enough(self) -> None:
        """The ordinary case works."""
        payload = InterventionRescheduleRequest(**VALID)

        assert payload.day == date(2026, 9, 14)
        assert payload.start_minute == 540
        assert payload.end_minute == 720

    def test_a_day_is_parsed_from_a_string(self) -> None:
        """The wire sends ISO dates."""
        payload = InterventionRescheduleRequest(**{**VALID, "day": "2026-09-14"})

        assert payload.day == date(2026, 9, 14)

    # ------------------------------------------------------------------ #
    #  The shape is the permission
    # ------------------------------------------------------------------ #

    def test_it_carries_no_quote_line(self) -> None:
        """**The visit is in the path and names its own line.**

        Notes:
            A ``quote_line_id`` here would be a second answer to "which piece of
            work", and one a household has no way to know. The manager-side
            payload does carry it, because a manager rescheduling from the quote
            screen is holding the line rather than the visit.
        """
        assert set(InterventionRescheduleRequest.model_fields) == {
            "day",
            "start_minute",
            "end_minute",
        }

    def test_it_cannot_cancel_anything(self) -> None:
        """Moving and cancelling are separate acts with separate routes.

        Notes:
            Folded together, a mistyped window would quietly remove a visit
            instead of moving it.
        """
        payload = InterventionRescheduleRequest(**{**VALID, "cancel": True})

        assert not hasattr(payload, "cancel")

    # ------------------------------------------------------------------ #
    #  day validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param("", id="Invalid - empty"),
        ],
    )
    def test_a_missing_day_is_refused(self, value: Any) -> None:
        """A reschedule with no day is not a reschedule.

        Args:
            value (Any): The rejected value.
        """
        with pytest.raises(MTInterventionRescheduleRequestInvalidDay):
            InterventionRescheduleRequest(**{**VALID, "day": value})

    # ------------------------------------------------------------------ #
    #  window validation
    # ------------------------------------------------------------------ #

    def test_an_empty_window_is_refused(self) -> None:
        """**An end at the start is no window, not a narrow one.**

        Notes:
            Accepted, the solver would be asked to fit the work into nothing
            and would report the visit unplaceable — which reads to the
            household as their change having been ignored rather than refused.
        """
        with pytest.raises(MTInterventionRescheduleRequestInvalidWindow):
            InterventionRescheduleRequest(
                **{**VALID, "start_minute": 540, "end_minute": 540}
            )

    def test_a_backwards_window_is_refused(self) -> None:
        """The end must fall after the start."""
        with pytest.raises(MTInterventionRescheduleRequestInvalidWindow):
            InterventionRescheduleRequest(
                **{**VALID, "start_minute": 720, "end_minute": 540}
            )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            pytest.param("start_minute", -1, id="start before midnight"),
            pytest.param("start_minute", 1440, id="start at midnight"),
            pytest.param("end_minute", 0, id="end at midnight"),
            pytest.param("end_minute", 1441, id="end past midnight"),
        ],
    )
    def test_a_window_outside_the_day_is_refused(self, field: str, value: int) -> None:
        """A window has to fall inside one day.

        Args:
            field (str): The bound under test.
            value (int): The out-of-range value.

        Notes:
            1440 is midnight at the end of the day, so it is a valid *end* and
            never a valid *start* — a visit cannot begin at the instant the day
            finishes.
        """
        with pytest.raises(MTInterventionRescheduleRequestInvalidWindow):
            InterventionRescheduleRequest(**{**VALID, field: value})

    def test_the_last_minute_of_the_day_is_a_valid_end(self) -> None:
        """Midnight closes the window it cannot open."""
        payload = InterventionRescheduleRequest(
            **{**VALID, "start_minute": 1380, "end_minute": 1440}
        )

        assert payload.end_minute == 1440

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            pytest.param("start_minute", "540", id="start as a string"),
            pytest.param("end_minute", 720.5, id="end as a float"),
            pytest.param("start_minute", True, id="start as a boolean"),
            pytest.param("end_minute", None, id="end missing"),
        ],
    )
    def test_a_non_integer_bound_is_refused(self, field: str, value: Any) -> None:
        """Minutes are integers, never coerced from something else.

        Args:
            field (str): The bound under test.
            value (Any): The rejected value.

        Notes:
            ``True`` is refused explicitly. It is an ``int`` in Python and would
            arrive as minute one, placing a visit at ten past midnight.
        """
        with pytest.raises(MTInterventionRescheduleRequestInvalidWindow):
            InterventionRescheduleRequest(**{**VALID, field: value})

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTInterventionRescheduleRequestInvalidDay,
            MTInterventionRescheduleRequestInvalidWindow,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit the family the API maps to 422.

        Args:
            exception_class (type): The exception under test.
        """
        assert issubclass(
            exception_class, MTInvalidInterventionRescheduleRequestException
        )

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_it_round_trips(self) -> None:
        """The payload survives a dump-and-rebuild unchanged."""
        payload = InterventionRescheduleRequest(**VALID)

        assert InterventionRescheduleRequest(**payload.model_dump()) == payload
