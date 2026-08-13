from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Dict

# Third-party imports
import pytest
from pydantic import ValidationError

# First-party imports
from models.enums import ServiceCategory
from models.schemas.exceptions import (
    MTInvalidQuoteCreateRequestException,
    MTQuoteCreateRequestInvalidCustomerId,
    MTQuoteCreateRequestInvalidLines,
    MTQuoteCreateRequestInvalidReference,
)
from models.schemas.requests.quoting.quote_create_request import QuoteCreateRequest
from tests.annotations import ModelInput

MONDAY = date(2026, 8, 3)


def _line() -> Dict[str, ModelInput]:
    """Return a service line, as a payload would carry it.

    Returns:
        Dict[str, ModelInput]: The raw line.
    """
    return {
        "intervention_type_id": "type-1",
        "name": "Toilette matin",
        "service_date": MONDAY.isoformat(),
        "earliest_start": "09:00",
        "latest_end": "12:00",
        "duration_minutes": 120,
        "service_category": ServiceCategory.NECESSITY.value,
    }


class TestQuoteCreateRequest:
    """Tests for the payload opening a new quote."""

    # ------------------------------------------------------------------ #
    #  The shape is the permission
    # ------------------------------------------------------------------ #

    def test_the_agency_cannot_be_chosen(self) -> None:
        """``company_id`` is absent, so no payload can name an agency.

        Notes:
            **This test is the rule.** The agency decides whose accepted work a
            planning run schedules and whose calendar it rewrites, so a caller
            able to set it could write a quote into another agency and have that
            agency's assistants sent out to deliver it. It is taken from the
            credential in the route, and the only way to guarantee that is for
            the payload to have nowhere to put one.
        """
        assert "company_id" not in QuoteCreateRequest.model_fields

    def test_a_quote_cannot_arrive_already_accepted(self) -> None:
        """``status`` is absent, so acceptance cannot skip the workflow.

        Notes:
            The route took a whole quote before this model existed, which meant
            a payload could carry ``status="accepted"`` and land straight in the
            planner without a manager ever ruling on it.
        """
        assert "status" not in QuoteCreateRequest.model_fields

    @pytest.mark.parametrize(
        "forbidden",
        [
            pytest.param("authored_by", id="authored_by"),
            pytest.param("validated_by", id="validated_by"),
            pytest.param("validated_at", id="validated_at"),
        ],
    )
    def test_authorship_cannot_be_claimed(self, forbidden: str) -> None:
        """Who wrote and who approved a quote are recorded, never sent."""
        assert forbidden not in QuoteCreateRequest.model_fields

    def test_it_carries_only_what_a_caller_may_choose(self) -> None:
        """A field added here silently widens what a payload can set."""
        assert set(QuoteCreateRequest.model_fields) == {
            "reference",
            "customer_id",
            "lines",
        }

    # ------------------------------------------------------------------ #
    #  reference
    # ------------------------------------------------------------------ #

    def test_the_reference_is_stripped(self) -> None:
        """Surrounding whitespace is removed."""
        payload = QuoteCreateRequest(reference="  D-2601  ", customer_id="customer-1")

        assert payload.reference == "D-2601"

    @pytest.mark.parametrize(
        "invalid_reference",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_an_invalid_reference_is_refused(
        self, invalid_reference: ModelInput
    ) -> None:
        """A quote number is what a customer quotes back on the phone."""
        with pytest.raises(MTQuoteCreateRequestInvalidReference):
            QuoteCreateRequest(reference=invalid_reference, customer_id="customer-1")

    def test_a_missing_reference_is_refused(self) -> None:
        """Absent is refused too, by the field being required."""
        with pytest.raises(ValidationError):
            QuoteCreateRequest(customer_id="customer-1")

    # ------------------------------------------------------------------ #
    #  customer_id
    # ------------------------------------------------------------------ #

    def test_the_customer_is_stripped(self) -> None:
        """Surrounding whitespace is removed."""
        payload = QuoteCreateRequest(reference="D-2601", customer_id="  customer-1  ")

        assert payload.customer_id == "customer-1"

    @pytest.mark.parametrize(
        "invalid_customer",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_an_invalid_customer_is_refused(self, invalid_customer: ModelInput) -> None:
        """A quote is an offer addressed to somebody."""
        with pytest.raises(MTQuoteCreateRequestInvalidCustomerId):
            QuoteCreateRequest(reference="D-2601", customer_id=invalid_customer)

    # ------------------------------------------------------------------ #
    #  lines
    # ------------------------------------------------------------------ #

    def test_a_quote_may_start_with_no_services(self) -> None:
        """The first save is usually before anything has been chosen.

        Notes:
            Refusing an empty list would make the screen unable to save a quote
            until it was finished, which is the opposite of how one is written.
        """
        payload = QuoteCreateRequest(reference="D-2601", customer_id="customer-1")

        assert payload.lines == []

    def test_the_services_are_parsed(self) -> None:
        """Each line is validated by the line model itself."""
        payload = QuoteCreateRequest(
            reference="D-2601", customer_id="customer-1", lines=[_line()]
        )

        assert len(payload.lines) == 1
        assert payload.lines[0].intervention_type_id == "type-1"

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
        with pytest.raises(MTQuoteCreateRequestInvalidLines):
            QuoteCreateRequest(
                reference="D-2601", customer_id="customer-1", lines=invalid_lines
            )

    # ------------------------------------------------------------------ #
    #  to_quote
    # ------------------------------------------------------------------ #

    def test_the_agency_comes_from_the_caller(self) -> None:
        """The one place a payload becomes a quote is the one that sets it."""
        payload = QuoteCreateRequest(reference="D-2601", customer_id="customer-1")

        assert payload.to_quote("company-7", "team-1").company_id == "company-7"

    def test_the_quote_is_built_as_a_draft(self) -> None:
        """Status is left to the quote's own default.

        Notes:
            A quote that arrived already accepted would have skipped every step
            that makes acceptance mean anything.
        """
        payload = QuoteCreateRequest(reference="D-2601", customer_id="customer-1")

        assert payload.to_quote("company-1", "team-1").status.value == "draft"

    def test_the_payloads_fields_are_carried_across(self) -> None:
        """What was asked for is what is built."""
        payload = QuoteCreateRequest(
            reference="D-2601", customer_id="customer-1", lines=[_line()]
        )

        quote = payload.to_quote("company-1", "team-1")

        assert quote.reference == "D-2601"
        assert quote.customer_id == "customer-1"
        assert len(quote.lines) == 1

    def test_the_built_quote_names_nobody_as_its_author(self) -> None:
        """Authorship is stamped by the service, from the credential."""
        payload = QuoteCreateRequest(reference="D-2601", customer_id="customer-1")

        assert payload.to_quote("company-1", "team-1").authored_by is None

    def test_the_lines_are_copied_rather_than_shared(self) -> None:
        """Editing the payload afterwards must not reach the quote.

        Notes:
            The list is handed to a model that stores it, so sharing the object
            would let a later append to the payload change a quote already built
            from it.
        """
        payload = QuoteCreateRequest(
            reference="D-2601", customer_id="customer-1", lines=[_line()]
        )

        quote = payload.to_quote("company-1", "team-1")
        payload.lines.clear()

        assert len(quote.lines) == 1

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTQuoteCreateRequestInvalidCustomerId,
            MTQuoteCreateRequestInvalidLines,
            MTQuoteCreateRequestInvalidReference,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the payload's own family base.

        Notes:
            The base is what ``ExceptionHandlers`` has a row for, so a new
            per-field exception answers 422 without anybody remembering to
            register it.
        """
        assert issubclass(exception_class, MTInvalidQuoteCreateRequestException)
