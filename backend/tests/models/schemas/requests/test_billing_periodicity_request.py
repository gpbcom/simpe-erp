from __future__ import annotations

# Standard library imports
from typing import Any

# Third-party imports
import pytest

# First-party imports
from models.enums import BillingPeriodicity
from models.schemas.exceptions import (
    MTBillingPeriodicityRequestInvalidPeriodicity,
    MTInvalidBillingPeriodicityRequestException,
)
from models.schemas.requests.customers.billing_periodicity_request import (
    BillingPeriodicityRequest,
)


class TestBillingPeriodicityRequest:
    """Tests for setting, or clearing, one customer's own granularity."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_an_empty_payload_puts_the_customer_back_on_the_agency(self) -> None:
        """**Null is a value here, not a field somebody forgot.**

        Notes:
            Sending nothing is how a manager takes an override off. If that
            read as "no change", an override could be set and never removed
            except by editing the record by hand — which is the point at which
            somebody starts billing a customer weekly forever.
        """
        payload = BillingPeriodicityRequest()

        assert payload.periodicity is None
        assert payload.follows_the_agency() is True

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("weekly", id="As the string the screen sends"),
            pytest.param(BillingPeriodicity.WEEKLY, id="As the enum member"),
        ],
    )
    def test_a_named_periodicity_is_kept(self, value: Any) -> None:
        """A granularity somebody chose survives whichever way it arrives."""
        payload = BillingPeriodicityRequest(periodicity=value)

        assert payload.periodicity is BillingPeriodicity.WEEKLY
        assert payload.follows_the_agency() is False

    # ------------------------------------------------------------------ #
    #  Validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("fortnightly", id="Invalid - not a periodicity"),
            pytest.param("Monthly", id="Invalid - the wrong case"),
            pytest.param(30, id="Invalid - a number of days"),
        ],
    )
    def test_an_unknown_periodicity_is_refused(self, value: Any) -> None:
        """Refused with the accepted values named, so a 422 is actionable."""
        with pytest.raises(MTBillingPeriodicityRequestInvalidPeriodicity) as raised:
            BillingPeriodicityRequest(periodicity=value)

        assert "weekly, monthly, yearly" in str(raised.value)

    def test_the_refusal_belongs_to_the_registered_family(self) -> None:
        """So the API answers 422 rather than 500.

        Notes:
            The family is what ``STATUS_BY_EXCEPTION`` holds a row for; the
            per-field exception is reached through the MRO. A member outside it
            would be a payload error answered as a server fault.
        """
        assert issubclass(
            MTBillingPeriodicityRequestInvalidPeriodicity,
            MTInvalidBillingPeriodicityRequestException,
        )
