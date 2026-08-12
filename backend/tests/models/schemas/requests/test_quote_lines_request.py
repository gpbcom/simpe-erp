from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Dict

# Third-party imports
import pytest

# First-party imports
from models.enums import ServiceCategory
from models.schemas.exceptions import (
    MTInvalidQuoteLinesRequestException,
    MTQuoteLinesRequestInvalidLines,
)
from models.schemas.requests.quoting.quote_lines_request import QuoteLinesRequest
from tests.annotations import ModelInput

MONDAY = date(2026, 8, 3)


def _line(name: str = "Toilette matin") -> Dict[str, ModelInput]:
    """Return a service line, as a payload would carry it.

    Args:
        name (str): What the service is called.

    Returns:
        Dict[str, ModelInput]: The raw line.
    """
    return {
        "intervention_type_id": "type-1",
        "name": name,
        "service_date": MONDAY.isoformat(),
        "earliest_start": "09:00",
        "latest_end": "12:00",
        "duration_minutes": 120,
        "service_category": ServiceCategory.NECESSITY.value,
    }


class TestQuoteLinesRequest:
    """Tests for the payload replacing a draft quote's services."""

    # ------------------------------------------------------------------ #
    #  The shape is the permission
    # ------------------------------------------------------------------ #

    def test_it_carries_only_the_lines(self) -> None:
        """A field added here silently widens what a repricing can change.

        Notes:
            **This test is the rule.** The route promised in prose that "only
            the lines are taken from the body" while accepting a whole quote, so
            the promise rested on the service remembering not to look. A body
            able to name an agency would let a repricing move a quote between
            agencies, which is why the promise had to become a type.
        """
        assert set(QuoteLinesRequest.model_fields) == {"lines"}

    @pytest.mark.parametrize(
        "forbidden",
        [
            pytest.param("company_id", id="company_id"),
            pytest.param("customer_id", id="customer_id"),
            pytest.param("reference", id="reference"),
            pytest.param("status", id="status"),
        ],
    )
    def test_nothing_but_the_lines_can_be_sent(self, forbidden: str) -> None:
        """Editing services cannot reassign or accept the quote."""
        assert forbidden not in QuoteLinesRequest.model_fields

    # ------------------------------------------------------------------ #
    #  lines
    # ------------------------------------------------------------------ #

    def test_the_services_are_parsed(self) -> None:
        """Each line is validated by the line model itself."""
        payload = QuoteLinesRequest(lines=[_line()])

        assert len(payload.lines) == 1
        assert payload.lines[0].name == "Toilette matin"

    def test_several_services_keep_their_order(self) -> None:
        """The order sent is the order stored.

        Notes:
            A quote is read as a document, and its lines are the order somebody
            typed them in.
        """
        payload = QuoteLinesRequest(lines=[_line("Matin"), _line("Soir")])

        assert [line.name for line in payload.lines] == ["Matin", "Soir"]

    def test_an_empty_list_is_a_real_edit(self) -> None:
        """Emptying a quote is how its last line is removed.

        Notes:
            Read as "leave the lines alone" instead, this would leave a line
            nobody could delete.
        """
        payload = QuoteLinesRequest(lines=[])

        assert payload.lines == []

    def test_an_omitted_list_is_the_same_as_an_empty_one(self) -> None:
        """There is no third state here, unlike a line's certifications."""
        assert QuoteLinesRequest().lines == []

    @pytest.mark.parametrize(
        "invalid_lines",
        [
            pytest.param("Toilette", id="Invalid - string"),
            pytest.param(7, id="Invalid - int"),
            pytest.param({"intervention_type_id": "type-1"}, id="Invalid - dict"),
        ],
    )
    def test_services_that_are_not_a_list_are_refused(
        self, invalid_lines: ModelInput
    ) -> None:
        """A single line sent unwrapped is a mistake, not one line."""
        with pytest.raises(MTQuoteLinesRequestInvalidLines):
            QuoteLinesRequest(lines=invalid_lines)

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    def test_the_exception_has_its_own_family(self) -> None:
        """Distinct from the creation payload's, though the check is the same.

        Notes:
            The two payloads are answered by different routes, and a caller
            reading the failure should be told which one it came from.
        """
        assert issubclass(
            MTQuoteLinesRequestInvalidLines, MTInvalidQuoteLinesRequestException
        )
