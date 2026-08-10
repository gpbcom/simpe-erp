from __future__ import annotations

# Standard library imports
from datetime import date

# Third-party imports
import pytest

# First-party imports
from models.schemas.exceptions import (
    MTQuoteHeaderRequestInvalidAutoRenew,
    MTQuoteHeaderRequestInvalidCustomer,
    MTQuoteHeaderRequestInvalidDate,
    MTQuoteHeaderRequestInvalidReference,
    MTQuoteHeaderRequestInvalidValidity,
)
from models.schemas.requests.quoting.quote_header_request import QuoteHeaderRequest


class TestAcceptingAHeaderEdit:
    """Tests for the payload that changes everything except lines and status."""

    def test_it_carries_the_whole_header(self) -> None:
        """Every field a screen shows about a quote, bar the lines."""
        payload = QuoteHeaderRequest(
            reference="D-2648",
            customer_id="customer-1",
            issued_on="2026-08-01",
            valid_until="2026-09-01",
            auto_renew=True,
        )

        assert payload.reference == "D-2648"
        assert payload.issued_on == date(2026, 8, 1)
        assert payload.auto_renew is True

    def test_the_dates_are_optional(self) -> None:
        """A drafted quote has not been issued and may never expire.

        Notes:
            An empty box means "not yet", not an error. Requiring them would
            make a quote un-saveable until somebody invented a date.
        """
        payload = QuoteHeaderRequest(reference="D-1", customer_id="c-1")

        assert payload.issued_on is None
        assert payload.valid_until is None

    def test_a_blank_date_string_is_read_as_absent(self) -> None:
        """A cleared date field arrives from a browser as an empty string."""
        payload = QuoteHeaderRequest(
            reference="D-1", customer_id="c-1", issued_on="", valid_until=""
        )

        assert payload.issued_on is None

    def test_whitespace_is_trimmed(self) -> None:
        """A reference is quoted back on the telephone, not copied with spaces."""
        payload = QuoteHeaderRequest(reference="  D-1  ", customer_id="  c-1  ")

        assert payload.reference == "D-1"
        assert payload.customer_id == "c-1"

    def test_auto_renew_defaults_to_off(self) -> None:
        """Renewing by itself is opt-in; an omitted flag must not commit."""
        payload = QuoteHeaderRequest(reference="D-1", customer_id="c-1")

        assert payload.auto_renew is False


class TestRefusingAnUnusableHeader:
    """Tests for the values that would leave a quote unusable."""

    @pytest.mark.parametrize("value", ["", "   ", None, 42])
    def test_a_missing_reference_is_refused(self, value: object) -> None:
        """It is the handle a customer and the planning report both use.

        Args:
            value (object): The rejected reference.
        """
        with pytest.raises(MTQuoteHeaderRequestInvalidReference):
            QuoteHeaderRequest(reference=value, customer_id="c-1")

    @pytest.mark.parametrize("value", ["", "   ", None, 7])
    def test_a_quote_addressed_to_nobody_is_refused(self, value: object) -> None:
        """Args:
        value (object): The rejected customer identifier.
        """
        with pytest.raises(MTQuoteHeaderRequestInvalidCustomer):
            QuoteHeaderRequest(reference="D-1", customer_id=value)

    @pytest.mark.parametrize("value", ["not-a-date", 20260801, ["2026-08-01"]])
    def test_a_date_that_is_not_a_date_is_refused(self, value: object) -> None:
        """Args:
        value (object): The rejected date.
        """
        with pytest.raises(MTQuoteHeaderRequestInvalidDate):
            QuoteHeaderRequest(
                reference="D-1", customer_id="c-1", issued_on=value
            )

    def test_a_quote_cannot_expire_before_it_was_issued(self) -> None:
        """The pair is only wrong together.

        Notes:
            Either date alone is fine, so nothing else refuses this. A quote
            that expired before it existed would simply never be acceptable,
            with no explanation on any screen.
        """
        with pytest.raises(MTQuoteHeaderRequestInvalidValidity):
            QuoteHeaderRequest(
                reference="D-1",
                customer_id="c-1",
                issued_on="2026-09-01",
                valid_until="2026-08-01",
            )

    def test_the_same_day_is_allowed(self) -> None:
        """A quote issued and expiring the same day is short, not invalid."""
        payload = QuoteHeaderRequest(
            reference="D-1",
            customer_id="c-1",
            issued_on="2026-08-01",
            valid_until="2026-08-01",
        )

        assert payload.valid_until == payload.issued_on

    @pytest.mark.parametrize("value", ["yes", 1, [], {}])
    def test_a_non_boolean_auto_renew_is_refused(self, value: object) -> None:
        """Args:
        value (object): The rejected flag.
        """
        with pytest.raises(MTQuoteHeaderRequestInvalidAutoRenew):
            QuoteHeaderRequest(
                reference="D-1", customer_id="c-1", auto_renew=value
            )
