from __future__ import annotations

# Standard library imports
from typing import Any

# Third-party imports
from pydantic import ValidationError
import pytest

# First-party imports
from models.enums import Weekday
from models.schemas.exceptions import (
    MTInvalidWorkingDaysRequestException,
    MTWorkingDaysRequestInvalidWeekdays,
)
from models.schemas.requests.hca.working_days_request import WorkingDaysRequest


class TestWorkingDaysRequest:
    """Tests for the payload declaring which days an assistant works."""

    def test_a_complete_week_is_accepted(self) -> None:
        """The ordinary case."""
        request = WorkingDaysRequest(
            working_weekdays=["monday", "tuesday", "wednesday"]
        )

        assert request.working_weekdays == [
            Weekday.MONDAY,
            Weekday.TUESDAY,
            Weekday.WEDNESDAY,
        ]

    def test_the_week_is_sorted_monday_first(self) -> None:
        """The order a client sent the boxes in is not a working week."""
        request = WorkingDaysRequest(working_weekdays=["saturday", "tuesday", "monday"])

        assert request.working_weekdays == [
            Weekday.MONDAY,
            Weekday.TUESDAY,
            Weekday.SATURDAY,
        ]

    def test_a_repeated_day_is_counted_once(self) -> None:
        """Two tickings of the same box are one working day."""
        request = WorkingDaysRequest(working_weekdays=["monday", "monday", "friday"])

        assert request.working_weekdays == [Weekday.MONDAY, Weekday.FRIDAY]

    def test_enum_members_are_accepted_as_well_as_strings(self) -> None:
        """A caller inside the process need not stringify first."""
        request = WorkingDaysRequest(working_weekdays=[Weekday.THURSDAY])

        assert request.working_weekdays == [Weekday.THURSDAY]

    def test_a_single_day_week_is_accepted(self) -> None:
        """Somebody who works one day a week is not an error."""
        request = WorkingDaysRequest(working_weekdays=["wednesday"])

        assert request.working_weekdays == [Weekday.WEDNESDAY]

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param([], id="Invalid - every box cleared"),
            pytest.param(["funday"], id="Invalid - not a weekday"),
            pytest.param(["monday", "mondee"], id="Invalid - one bad entry"),
            pytest.param("monday", id="Invalid - a bare string, not a list"),
            pytest.param(None, id="Invalid - missing"),
            pytest.param(3, id="Invalid - not a collection"),
        ],
    )
    def test_an_unusable_week_is_refused(self, value: Any) -> None:
        """A week the assistant cannot have worked is a 422, not a default.

        Args:
            value (Any): The rejected payload.

        Notes:
            The empty list is the one that matters. Clearing every box is a
            statement, and its two readings — "I work no days" and "put me
            back on the standard week" — are opposites. Refusing makes the
            client say which it meant.
        """
        with pytest.raises(MTWorkingDaysRequestInvalidWeekdays):
            WorkingDaysRequest(working_weekdays=value)

    def test_the_payload_is_required(self) -> None:
        """There is no default working week on the way in.

        Notes:
            The field has no default deliberately. A ``PUT`` with an empty body
            would otherwise silently reset somebody's week to Monday-to-Friday.

            This one raises Pydantic's own ``ValidationError`` rather than the
            model's exception, and that is not an inconsistency to fix: a
            ``mode="before"`` validator never runs for a field that is absent,
            so there is no point at which this model could raise its own. Both
            leave the API as a 422.
        """
        with pytest.raises(ValidationError):
            WorkingDaysRequest()

    def test_every_leaf_shares_one_base(self) -> None:
        """One except clause catches everything this payload raises."""
        assert issubclass(
            MTWorkingDaysRequestInvalidWeekdays,
            MTInvalidWorkingDaysRequestException,
        )
