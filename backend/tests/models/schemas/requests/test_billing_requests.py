from __future__ import annotations

# Standard library imports
from datetime import date
from decimal import Decimal

# Third-party imports
import pytest

# First-party imports
from models.enums import BillingPeriodicity, BillStatus
from models.schemas.exceptions import (
    MTBillAcceptedRequestInvalidId,
    MTBillDispatchResponseInvalidId,
    MTBillFilterInvalidDate,
    MTBillFilterInvalidFlag,
    MTBillFilterInvalidFragment,
    MTBillFilterInvalidStatus,
    MTBillGenerationRequestInvalidCustomers,
    MTBillGenerationRequestInvalidDate,
    MTBillingSettingsRequestInvalidIndemnity,
    MTBillingSettingsRequestInvalidPaymentTerms,
    MTBillingSettingsRequestInvalidPenaltyMultiplier,
    MTBillingSettingsRequestInvalidPeriodicity,
    MTBillStatusRequestInvalidStatus,
)
from models.schemas.requests.billing.bill_accepted_request import (
    BillAcceptedRequest,
)
from models.schemas.requests.billing.bill_filter import BillFilter
from models.schemas.requests.billing.bill_generation_request import (
    BillGenerationRequest,
)
from models.schemas.requests.billing.bill_status_request import BillStatusRequest
from models.schemas.requests.billing.billing_settings_request import (
    BillingSettingsRequest,
)
from models.schemas.responses.billing.bill_dispatch_response import (
    BillDispatchResponse,
)
from models.settings.billing_settings import BillingSettings
from tests.annotations import ModelInput


class TestBillingSettingsRequest:
    """Tests for the payload changing the invoicing rules."""

    def test_every_field_defaults_to_the_stored_model_s_value(self) -> None:
        """A partial payload must not reset the fields it omits.

        Notes:
            The whole rule set is sent on every save, and defaults are what stop
            a manager who changed only the periodicity from silently rewriting
            the payment terms printed on every invoice.
        """
        request = BillingSettingsRequest()
        stored = BillingSettings()
        assert request.periodicity is stored.periodicity
        assert request.payment_terms_days == stored.payment_terms_days
        assert request.late_penalty_multiplier == stored.late_penalty_multiplier
        assert request.recovery_indemnity_eur == stored.recovery_indemnity_eur
        assert request.escompte_offered is stored.escompte_offered

    @pytest.mark.parametrize(
        ("field", "value", "expected"),
        [
            pytest.param(
                "periodicity",
                "fortnightly",
                MTBillingSettingsRequestInvalidPeriodicity,
                id="Invalid - unknown periodicity",
            ),
            pytest.param(
                "payment_terms_days",
                90,
                MTBillingSettingsRequestInvalidPaymentTerms,
                id="Invalid - terms above the ceiling",
            ),
            pytest.param(
                "payment_terms_days",
                "30",
                MTBillingSettingsRequestInvalidPaymentTerms,
                id="Invalid - terms as a string",
            ),
            pytest.param(
                "late_penalty_multiplier",
                0,
                MTBillingSettingsRequestInvalidPenaltyMultiplier,
                id="Invalid - multiplier below the floor",
            ),
            pytest.param(
                "recovery_indemnity_eur",
                Decimal("-1"),
                MTBillingSettingsRequestInvalidIndemnity,
                id="Invalid - negative indemnity",
            ),
        ],
    )
    def test_a_bad_payload_names_its_own_field(
        self, field: str, value: ModelInput, expected: type
    ) -> None:
        """The request repeats the stored model's bounds on purpose.

        Notes:
            This is the outer of two gates. Deferring to the stored model would
            still refuse the value, but the caller would get something vaguer
            from deeper in the stack instead of a 422 naming the field they got
            wrong.
        """
        with pytest.raises(expected):
            BillingSettingsRequest(**{field: value})

    def test_applying_a_payload_re_runs_the_stored_validators(self) -> None:
        """The merge goes through ``model_validate``, never ``model_copy``.

        Notes:
            ``model_copy`` does not re-run validators, so an update taking that
            route would store a value the stored model would have refused, and
            the refusal would only surface the next time somebody read it.
        """
        applied = BillingSettingsRequest(
            periodicity=BillingPeriodicity.WEEKLY, payment_terms_days=45
        ).apply_to(BillingSettings(), actor="manager@example.test")
        assert applied.periodicity is BillingPeriodicity.WEEKLY
        assert applied.payment_terms_days == 45
        assert applied.updated_by == "manager@example.test"
        assert applied.id == BillingSettings.SINGLETON_ID

    def test_applying_a_payload_records_who_changed_the_terms(self) -> None:
        """An edit to what customers are told is somebody's decision."""
        applied = BillingSettingsRequest().apply_to(
            BillingSettings(updated_by="someone-else"), actor="manager-1"
        )
        assert applied.updated_by == "manager-1"


class TestBillGenerationRequest:
    """Tests for the payload asking for a period to be billed."""

    def test_a_run_is_asked_for_by_naming_a_day(self) -> None:
        """The window comes from the agency's own rule, not from the caller.

        Notes:
            A caller who could name arbitrary bounds could invoice a fortnight
            the settings do not describe, producing a window nobody could
            reproduce afterwards.
        """
        request = BillGenerationRequest(reference_date=date(2026, 3, 9))
        assert request.reference_date == date(2026, 3, 9)
        assert request.customer_ids is None

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(None, id="Invalid - None"),
            pytest.param(20260309, id="Invalid - int"),
            pytest.param(object(), id="Invalid - object"),
        ],
    )
    def test_a_run_without_a_day_is_refused(self, value: ModelInput) -> None:
        """There is no default period; billing the wrong month is expensive."""
        with pytest.raises(MTBillGenerationRequestInvalidDate):
            BillGenerationRequest(reference_date=value)

    def test_omitting_the_customers_means_all_of_them(self) -> None:
        """The ordinary run bills everybody with work in the period."""
        request = BillGenerationRequest(reference_date=date(2026, 3, 9))
        assert request.covers("customer-1") is True

    def test_naming_customers_restricts_the_run_to_them(self) -> None:
        """Re-running one customer must not re-bill the whole book."""
        request = BillGenerationRequest(
            reference_date=date(2026, 3, 9), customer_ids=["customer-1"]
        )
        assert request.covers("customer-1") is True
        assert request.covers("customer-2") is False

    def test_an_empty_customer_list_is_refused(self) -> None:
        """ "Bill nobody" and "bill everybody" are a month of invoicing apart.

        Notes:
            Normalised to ``None`` this would read as "everybody", which is the
            opposite of what an empty list says. A caller meaning everybody
            omits the field.
        """
        with pytest.raises(MTBillGenerationRequestInvalidCustomers):
            BillGenerationRequest(reference_date=date(2026, 3, 9), customer_ids=[])

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("customer-1", id="Invalid - a bare string"),
            pytest.param([""], id="Invalid - an empty identifier"),
            pytest.param([7], id="Invalid - a number"),
        ],
    )
    def test_an_unusable_customer_list_is_refused(self, value: ModelInput) -> None:
        """A restriction nobody can resolve is worse than none."""
        with pytest.raises(MTBillGenerationRequestInvalidCustomers):
            BillGenerationRequest(reference_date=date(2026, 3, 9), customer_ids=value)

    def test_a_repeated_customer_is_named_once(self) -> None:
        """One customer asked for twice is still one customer."""
        request = BillGenerationRequest(
            reference_date=date(2026, 3, 9),
            customer_ids=["customer-1", "customer-1"],
        )
        assert request.customer_ids == ["customer-1"]


class TestBillStatusRequest:
    """Tests for the payload moving a bill along its lifecycle."""

    def test_the_payload_names_only_the_destination(self) -> None:
        """Whether the move is legal is decided against the stored bill.

        Notes:
            A screen showing a stale row would otherwise send a transition that
            was legal when it was rendered and is not any more.
        """
        request = BillStatusRequest(status=BillStatus.ACCEPTED)
        assert request.status is BillStatus.ACCEPTED

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(None, id="Invalid - None"),
            pytest.param("archived", id="Invalid - unknown status"),
            pytest.param("", id="Invalid - empty"),
        ],
    )
    def test_a_missing_or_unknown_status_is_refused(self, value: ModelInput) -> None:
        """A status change whose whole content is missing is an empty order."""
        with pytest.raises(MTBillStatusRequestInvalidStatus):
            BillStatusRequest(status=value)


class TestBillFilter:
    """Tests for what narrows the bill list."""

    def test_an_unfiltered_request_narrows_nothing(self) -> None:
        """An empty filter is the plain list, not an empty one."""
        assert BillFilter().is_empty() is True

    def test_a_cleared_control_is_not_applied(self) -> None:
        """A select reset to its blank option submits an empty string.

        Notes:
            Answering 422 for it would put an error where a bill list belongs,
            every time somebody cleared a filter.
        """
        assert BillFilter(status="", number="", period_start="").is_empty() is True

    @pytest.mark.parametrize(
        ("field", "value", "expected"),
        [
            pytest.param(
                "status",
                "archived",
                MTBillFilterInvalidStatus,
                id="Invalid - unknown status",
            ),
            pytest.param(
                "number", 7, MTBillFilterInvalidFragment, id="Invalid - a number"
            ),
            pytest.param(
                "is_sent",
                "perhaps",
                MTBillFilterInvalidFlag,
                id="Invalid - not a boolean",
            ),
            pytest.param(
                "period_start",
                20260301,
                MTBillFilterInvalidDate,
                id="Invalid - not a date",
            ),
        ],
    )
    def test_an_unusable_filter_is_refused(
        self, field: str, value: ModelInput, expected: type
    ) -> None:
        """A filter the server cannot narrow by is the caller's to correct."""
        with pytest.raises(expected):
            BillFilter(**{field: value})

    def test_a_status_filter_is_coerced(self) -> None:
        """The wire carries the value; the filter carries the member."""
        assert BillFilter(status="paid").status is BillStatus.PAID

    def test_the_period_bounds_narrow_by_the_window_billed(self) -> None:
        """ "Show me March" means the care delivered in March.

        Notes:
            Not the invoice date, which for a March period is some day in April
            and is not what anybody is asking about.
        """
        narrowed = BillFilter(period_start=date(2026, 3, 1), period_end="2026-03-31")
        assert narrowed.period_start == date(2026, 3, 1)
        assert narrowed.period_end == date(2026, 3, 31)
        assert narrowed.is_empty() is False


class TestBillWebhookSchemas:
    """Tests for what travels between the worker and the webhook."""

    def test_the_announcement_carries_an_identifier_and_nothing_else(
        self,
    ) -> None:
        """The endpoint re-reads the bill rather than trusting the payload.

        Notes:
            Amounts on the wire would be a second copy of the invoice, one that
            could disagree with the stored one and decide what a customer is
            emailed.
        """
        assert BillAcceptedRequest(bill_id="  bill-1 ").bill_id == "bill-1"

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(None, id="Invalid - None"),
            pytest.param("", id="Invalid - empty"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_an_unidentified_announcement_is_refused(self, value: ModelInput) -> None:
        """An announcement naming no bill sends nothing to nobody."""
        with pytest.raises(MTBillAcceptedRequestInvalidId):
            BillAcceptedRequest(bill_id=value)

    def test_a_dispatch_reports_what_actually_happened(self) -> None:
        """The flag is the outcome, not the attempt.

        Notes:
            A bill whose delivery failed answers ``False`` and stays where its
            approval left it, so the list shows an invoice approved but not yet
            out — which is the truth and is actionable.
        """
        assert BillDispatchResponse(bill_id="bill-1").sent is False
        assert BillDispatchResponse(bill_id="bill-1", sent=True).sent is True

    def test_a_dispatch_names_the_bill_it_was_for(self) -> None:
        """A count with no identifier cannot be reconciled with anything."""
        with pytest.raises(MTBillDispatchResponseInvalidId):
            BillDispatchResponse(bill_id="")
