from __future__ import annotations

# Standard library imports
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Dict

# Third-party imports
import pytest

# First-party imports
from models.billing.bill import Bill
from models.billing.bill_line import BillLine
from models.billing.exceptions import (
    MTBillInvalidAddress,
    MTBillInvalidAmount,
    MTBillInvalidCustomer,
    MTBillInvalidDate,
    MTBillInvalidDocument,
    MTBillInvalidDueDate,
    MTBillInvalidId,
    MTBillInvalidLinePeriod,
    MTBillInvalidLines,
    MTBillInvalidMoment,
    MTBillInvalidNumber,
    MTBillInvalidOperationNature,
    MTBillInvalidRecipient,
    MTBillInvalidShare,
    MTBillInvalidPeriod,
    MTBillInvalidPeriodicity,
    MTBillInvalidSequence,
    MTBillInvalidStatus,
    MTBillInvalidTotals,
)
from models.enums import (
    BillingPeriodicity,
    BillStatus,
    OperationNature,
    ServiceCategory,
)

ADDRESS: Dict[str, Any] = {
    "street": "1 rue des Lilas",
    "postal_code": "75011",
    "city": "Paris",
    "country": "France",
}


def a_charge(
    service_date: date = date(2026, 3, 9),
    total_ht: str = "63.82",
    vat_rate: str = "0.055",
    vat_amount: str = "3.51",
    **overrides: Any,
) -> BillLine:
    """Build one priced charge.

    Args:
        service_date (date): The day the service was sold for.
        total_ht (str): The line total excluding tax.
        vat_rate (str): The rate the tax was charged at.
        vat_amount (str): The tax on the line.
        **overrides: Fields to replace on the default charge.

    Returns:
        BillLine: A charge a bill accepts.
    """
    payload: Dict[str, Any] = {
        "quote_line_id": "quote-line-1",
        "name": "Aide à la toilette",
        "service_category": ServiceCategory.NECESSITY,
        "service_date": service_date,
        "duration_minutes": 120,
        "hourly_rate_ht": Decimal("31.91"),
        "total_ht": Decimal(total_ht),
        "vat_rate": Decimal(vat_rate),
        "vat_amount": Decimal(vat_amount),
        "total_ttc": Decimal(total_ht) + Decimal(vat_amount),
    }
    payload.update(overrides)
    return BillLine(**payload)


def a_bill(**overrides: Any) -> Dict[str, Any]:
    """Build the payload of a March invoice carrying one charge.

    Args:
        **overrides: Fields to replace on the default payload.

    Returns:
        Dict[str, Any]: A payload ``Bill`` accepts.
    """
    lines = overrides.pop("lines", [a_charge()])
    payload: Dict[str, Any] = {
        "company_id": "company-1",
        "customer_id": "customer-1",
        "number": "FA-2026-000001",
        "sequence": 1,
        "sequence_year": 2026,
        "periodicity": BillingPeriodicity.MONTHLY,
        "period_start": date(2026, 3, 1),
        "period_end": date(2026, 3, 31),
        "issued_on": date(2026, 4, 1),
        "due_on": date(2026, 5, 1),
        "customer_full_name": "Jeanne Vincent",
        "customer_address": ADDRESS,
        "recipient": {"name": "Jeanne Vincent", "address": ADDRESS},
        "lines": lines,
        "total_ht": sum((line.total_ht for line in lines), Decimal("0.00")),
        "total_vat": sum((line.vat_amount for line in lines), Decimal("0.00")),
        "total_ttc": sum((line.total_ttc for line in lines), Decimal("0.00")),
    }
    payload.update(overrides)
    return payload


class TestBillIdentity:
    """Tests for the parts of an invoice that make it findable."""

    def test_the_number_is_upper_cased(self) -> None:
        """One invoice must not exist under two spellings.

        Notes:
            ``fa-2026-000012`` and ``FA-2026-000012`` reaching the store as
            different rows would look like two invoices for one period.
        """
        assert Bill(**a_bill(number="fa-2026-000012")).number == "FA-2026-000012"

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(None, id="Invalid - None"),
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - whitespace"),
        ],
    )
    def test_an_invoice_without_a_number_is_refused(self, value: Any) -> None:
        """A document with no number is outside the legal series."""
        with pytest.raises(MTBillInvalidNumber):
            Bill(**a_bill(number=value))

    @pytest.mark.parametrize(
        "field",
        [
            pytest.param("company_id", id="the issuing agency"),
            pytest.param("customer_id", id="the billed customer"),
        ],
    )
    def test_both_parties_are_required(self, field: str) -> None:
        """An invoice names who issued it and who owes it.

        Notes:
            The agency is not reachable through the customer — a customer record
            carries none — so an invoice that did not name its issuer could not
            be listed, scoped or numbered.
        """
        with pytest.raises(MTBillInvalidId):
            Bill(**a_bill(**{field: None}))

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(-1, id="Invalid - negative"),
            pytest.param(True, id="Invalid - bool"),
            pytest.param("1", id="Invalid - string"),
        ],
    )
    def test_the_sequence_starts_at_one(self, value: Any) -> None:
        """The series counts documents issued, so there is no position zero."""
        with pytest.raises(MTBillInvalidSequence):
            Bill(**a_bill(sequence=value))

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(202, id="Invalid - three digits"),
            pytest.param(99999, id="Invalid - five digits"),
            pytest.param("2026", id="Invalid - string"),
        ],
    )
    def test_the_series_year_is_bounded(self, value: Any) -> None:
        """The year is half of what makes a number unique.

        Notes:
            A typo landing in year 202 would open a second series nobody would
            ever find again, and the gap it left in the real one is the thing
            French numbering forbids.
        """
        with pytest.raises(MTBillInvalidSequence):
            Bill(**a_bill(sequence_year=value))

    def test_the_customer_is_named_not_just_identified(self) -> None:
        """An invoice prints a name somebody recognises as their own."""
        with pytest.raises(MTBillInvalidCustomer):
            Bill(**a_bill(customer_full_name="   "))

    def test_the_billing_address_is_a_real_address(self) -> None:
        """Where the invoice went is part of what was sent."""
        with pytest.raises(MTBillInvalidAddress):
            Bill(**a_bill(customer_address="1 rue des Lilas, Paris"))

    def test_the_name_and_address_are_copies(self) -> None:
        """A customer who moves must not rewrite last quarter's invoice.

        Notes:
            The same reasoning as an intervention copying the assistant's name:
            a document is a record of what was sent, not a live join.
        """
        bill = Bill(**a_bill())
        assert bill.customer_full_name == "Jeanne Vincent"
        assert bill.customer_address.city == "Paris"


class TestBillPeriod:
    """Tests for the window an invoice charges for."""

    def test_a_window_may_be_a_single_day(self) -> None:
        """Both bounds are inclusive, so one day is a legitimate period."""
        bill = Bill(
            **a_bill(
                period_start=date(2026, 3, 9),
                period_end=date(2026, 3, 9),
            )
        )
        assert bill.describe_period() == "09/03/2026 - 09/03/2026"

    def test_a_reversed_window_is_refused(self) -> None:
        """A period ending before it starts charges for nothing."""
        with pytest.raises(MTBillInvalidPeriod):
            Bill(**a_bill(period_end=date(2026, 2, 1)))

    def test_payment_may_not_fall_due_before_the_invoice_is_written(
        self,
    ) -> None:
        """An invoice overdue on the day it is issued contradicts its terms.

        Notes:
            It would start its own late-payment penalties running, which is the
            one thing the printed terms promise it will not do.
        """
        with pytest.raises(MTBillInvalidDueDate):
            Bill(**a_bill(due_on=date(2026, 3, 1)))

    def test_a_charge_outside_the_window_is_refused(self) -> None:
        """**This is the time pro-rata, as an invariant.**

        Notes:
            A quote line is a single dated service, so "only the part inside the
            window is billed" is a date filter — and a filter is something a
            service can get wrong quietly. Checked here too, a caller that
            resolved the window badly cannot write a bill charging the next
            period's work: the bill refuses to be built at all, months before
            anybody reconciles it.
        """
        with pytest.raises(MTBillInvalidLinePeriod):
            Bill(**a_bill(lines=[a_charge(service_date=date(2026, 4, 2))]))

    @pytest.mark.parametrize(
        "service_date",
        [
            pytest.param(date(2026, 3, 1), id="the first day of the window"),
            pytest.param(date(2026, 3, 31), id="the last day of the window"),
        ],
    )
    def test_a_charge_on_either_bound_is_accepted(self, service_date: date) -> None:
        """The window contains both of its own ends.

        Notes:
            An exclusive end would drop the 31st of every month, which is a day
            of care nobody would be charged for and nobody would notice.
        """
        bill = Bill(**a_bill(lines=[a_charge(service_date=service_date)]))
        assert len(bill.lines) == 1

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(None, id="Invalid - None"),
            pytest.param(20260301, id="Invalid - int"),
        ],
    )
    def test_a_period_bound_must_be_a_date(self, value: Any) -> None:
        """Only a date delimits a period."""
        with pytest.raises(MTBillInvalidDate):
            Bill(**a_bill(period_start=value))

    def test_an_unknown_periodicity_is_refused(self) -> None:
        """The window has to come from a rule the application knows."""
        with pytest.raises(MTBillInvalidPeriodicity):
            Bill(**a_bill(periodicity="fortnightly"))


class TestBillTotals:
    """Tests for the amounts an invoice states."""

    def test_the_totals_must_equal_the_lines(self) -> None:
        """Stored totals are only safe if they were right when written.

        Notes:
            They are stored rather than computed so an issued invoice reprints
            identically for ever; this is what stops a line being added without
            them, or a rounding path drifting, and a customer finding it by
            adding up the column themselves.
        """
        with pytest.raises(MTBillInvalidTotals):
            Bill(**a_bill(total_ht=Decimal("99.99")))

    @pytest.mark.parametrize("field", list(Bill.MONEY_FIELDS))
    def test_every_total_is_required(self, field: str) -> None:
        """An invoice with a blank total is not an invoice."""
        with pytest.raises(MTBillInvalidAmount):
            Bill(**a_bill(**{field: None}))

    def test_a_negative_total_is_refused(self) -> None:
        """A credit is a credit note, not an invoice with a minus sign."""
        with pytest.raises(MTBillInvalidAmount):
            Bill(**a_bill(total_ht=Decimal("-1.00")))

    def test_vat_is_broken_down_by_rate(self) -> None:
        """A French invoice states the tax per rate, never as one figure.

        Notes:
            A home-care invoice routinely carries both — necessity assistance at
            5.5% beside comfort work at 20% — and one merged figure would make
            the document non-conforming.
        """
        lines = [
            a_charge(total_ht="100.00", vat_rate="0.055", vat_amount="5.50"),
            a_charge(total_ht="200.00", vat_rate="0.20", vat_amount="40.00"),
            a_charge(total_ht="50.00", vat_rate="0.055", vat_amount="2.75"),
        ]
        breakdown = Bill(**a_bill(lines=lines)).vat_by_rate()
        assert breakdown == [
            (Decimal("0.055"), Decimal("150.00"), Decimal("8.25")),
            (Decimal("0.20"), Decimal("200.00"), Decimal("40.00")),
        ]

    def test_the_breakdown_reads_the_stored_rate(self) -> None:
        """Grouping on the category would restate history after a rate change."""
        line = a_charge(
            service_category=ServiceCategory.NECESSITY,
            total_ht="100.00",
            vat_rate="0.20",
            vat_amount="20.00",
        )
        assert Bill(**a_bill(lines=[line])).vat_by_rate()[0][0] == Decimal("0.20")

    def test_an_empty_invoice_totals_zero_and_says_so(self) -> None:
        """Nothing delivered is nothing owed, and no number is burned on it."""
        bill = Bill(
            **a_bill(
                lines=[],
                total_ht=Decimal("0.00"),
                total_vat=Decimal("0.00"),
                total_ttc=Decimal("0.00"),
            )
        )
        assert bill.is_empty() is True
        assert bill.vat_by_rate() == []

    def test_lines_must_be_a_list(self) -> None:
        """A single charge is not a set of charges."""
        payload = a_bill()
        payload["lines"] = {"name": "Aide à la toilette"}
        with pytest.raises(MTBillInvalidLines):
            Bill(**payload)

    def test_total_minutes_sums_the_care_charged_for(self) -> None:
        """The hours are what a customer checks the amount against."""
        lines = [a_charge(), a_charge(duration_minutes=60)]
        assert Bill(**a_bill(lines=lines)).total_minutes() == 180


class TestBillLifecycle:
    """Tests for where an invoice has reached commercially."""

    def test_a_new_invoice_waits_to_be_validated(self) -> None:
        """Nothing reaches a customer before somebody approves it."""
        assert Bill(**a_bill()).status is BillStatus.TO_BE_VALIDATED

    def test_a_missing_status_never_falls_open(self) -> None:
        """The fallback is the first status and never a later one.

        Notes:
            Defaulting to anything past validation would put an invoice nobody
            approved into the post — the failure the whole status exists to
            prevent.
        """
        assert Bill(**a_bill(status=None)).status is BillStatus.TO_BE_VALIDATED

    def test_an_unknown_status_is_refused(self) -> None:
        """Only the four statuses the lifecycle defines are storable."""
        with pytest.raises(MTBillInvalidStatus):
            Bill(**a_bill(status="archived"))

    @pytest.mark.parametrize(
        "status",
        [
            pytest.param(BillStatus.ACCEPTED, id="accepted"),
            pytest.param(BillStatus.WAITING_PAYMENT, id="awaiting payment"),
            pytest.param(BillStatus.PAID, id="paid"),
        ],
    )
    def test_a_validated_invoice_must_have_a_document(self, status: BillStatus) -> None:
        """Nobody validates an invoice they cannot read.

        Notes:
            A number issued against a document that was never produced is a gap
            in a series that forbids gaps.
        """
        with pytest.raises(MTBillInvalidDocument):
            Bill(**a_bill(status=status, document_key=None))

    def test_an_invoice_awaiting_validation_may_have_no_document_yet(
        self,
    ) -> None:
        """There is an instant between the record and the rendered document."""
        assert Bill(**a_bill(document_key=None)).document_key is None

    def test_a_sent_invoice_reports_itself_as_sent(self) -> None:
        """``is_sent`` reads the timestamp, not the status.

        Notes:
            The two disagree on purpose: a bill a manager pushed to awaiting
            payment by hand while the mail server was down is awaited, but was
            never sent from here, and somebody chasing what has actually gone out
            needs the second answer.
        """
        sent = Bill(
            **a_bill(
                status=BillStatus.WAITING_PAYMENT,
                document_key="invoices/company-1/abc.pdf",
                sent_at=datetime(2026, 4, 2, 9, 0, tzinfo=timezone.utc),
            )
        )
        pushed_by_hand = Bill(
            **a_bill(
                status=BillStatus.WAITING_PAYMENT,
                document_key="invoices/company-1/abc.pdf",
            )
        )
        assert sent.is_sent() is True
        assert pushed_by_hand.is_sent() is False

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(20260402, id="Invalid - int"),
            pytest.param(object(), id="Invalid - object"),
        ],
    )
    def test_a_timestamp_must_be_a_moment(self, value: Any) -> None:
        """Only a datetime or an ISO string records when something happened."""
        with pytest.raises(MTBillInvalidMoment):
            Bill(**a_bill(sent_at=value))

    def test_the_audit_trail_is_optional_but_never_blank(self) -> None:
        """Who approved an invoice outlives the account that did it.

        Notes:
            Stored as a string rather than a foreign key for exactly that
            reason; a blank one would be the audit trail silently absent.
        """
        assert Bill(**a_bill(validated_by=None)).validated_by is None
        with pytest.raises(MTBillInvalidId):
            Bill(**a_bill(validated_by="  "))


class TestBillPresentation:
    """Tests for how an invoice reads."""

    def test_charges_are_printed_in_the_order_they_happened(self) -> None:
        """A customer reads an invoice as a diary of their month."""
        lines = [
            a_charge(service_date=date(2026, 3, 20)),
            a_charge(service_date=date(2026, 3, 2)),
            a_charge(service_date=date(2026, 3, 11)),
        ]
        ordered = Bill(**a_bill(lines=lines)).sorted_lines()
        assert [line.service_date.day for line in ordered] == [2, 11, 20]

    def test_a_charge_with_no_visit_sorts_to_the_start_of_its_day(self) -> None:
        """A service the planner never placed has no time of day.

        Notes:
            It sorts to the start of its own day, which is where a reader looks
            for a service that has no hours printed beside it.
        """
        placed = a_charge(
            service_date=date(2026, 3, 9),
            day=date(2026, 3, 9),
            start_time=time(14, 0),
            end_time=time(16, 0),
        )
        unplaced = a_charge(service_date=date(2026, 3, 9), name="Courses")
        ordered = Bill(**a_bill(lines=[placed, unplaced])).sorted_lines()
        assert ordered[0].name == "Courses"

    def test_the_period_is_printed_the_way_a_reader_writes_a_date(
        self,
    ) -> None:
        """French law requires the date of performance on a periodic invoice."""
        assert Bill(**a_bill()).describe_period() == "01/03/2026 - 31/03/2026"

    def test_the_currency_is_stated_once_for_the_whole_document(self) -> None:
        """Every amount on an invoice is in one currency."""
        assert Bill.CURRENCY == "EUR"


class TestTheStructuredInvoiceFields:
    """Tests for what the electronic-invoicing reform added to a bill."""

    def test_an_invoice_covers_services_unless_told_otherwise(self) -> None:
        """**The default decides when the VAT falls due.**

        Notes:
            On services the tax is exigible on collection; on goods, on
            delivery. Defaulting to goods would move the exigibility of every
            invoice this agency issues a month early.
        """
        bill = Bill(**a_bill())

        assert bill.operation_nature is OperationNature.SERVICES
        assert bill.operation_nature.includes_services() is True

    def test_an_unknown_operation_nature_is_refused(self) -> None:
        """A mandatory mention is not somewhere to guess."""
        with pytest.raises(MTBillInvalidOperationNature):
            Bill(**a_bill(operation_nature="subscription"))

    def test_an_invoice_must_name_who_owes_it(self) -> None:
        """**Required rather than defaulted to the customer.**

        Notes:
            - Defaulting would hide the choice from the one place it matters: a
              funded arrangement, where the payer is a département and the
              household would silently be invoiced for work somebody else pays
              for.
            - An explicit ``null`` is what this asserts, because that is what a
              payload can carry. A key left out entirely is refused by Pydantic
              before any validator runs — true of every required field on this
              model, and the reason the check exists here as well.
        """
        with pytest.raises(MTBillInvalidRecipient):
            Bill(**a_bill(recipient=None))

    def test_a_recipient_that_is_not_one_is_refused(self) -> None:
        """A name is not a party: the identifiers travel with it."""
        with pytest.raises(MTBillInvalidRecipient):
            Bill(**a_bill(recipient="Jeanne Vincent"))

    def test_a_household_paying_its_own_bill_is_reported_not_transmitted(
        self,
    ) -> None:
        """Which is most of this agency's revenue."""
        bill = Bill(**a_bill())

        assert bill.requires_electronic_invoice() is False
        assert bill.amount_due() == bill.total_ttc

    def test_a_funded_recipient_is_transmitted_and_owes_its_share(self) -> None:
        """The regime follows the buyer, not the person cared for."""
        bill = Bill(
            **a_bill(
                recipient={
                    "kind": "public",
                    "name": "Conseil départemental de Paris",
                    "address": ADDRESS,
                    "siren": "130025265",
                    "share_ttc": "10.00",
                }
            )
        )

        assert bill.requires_electronic_invoice() is True
        assert bill.amount_due() == Decimal("10.00")

    def test_a_share_above_the_total_is_refused(self) -> None:
        """Arithmetic nobody can reconcile, caught where it is written."""
        with pytest.raises(MTBillInvalidShare):
            Bill(
                **a_bill(
                    recipient={
                        "kind": "public",
                        "name": "Conseil départemental de Paris",
                        "address": ADDRESS,
                        "siren": "130025265",
                        "share_ttc": "100000.00",
                    }
                )
            )

    def test_a_share_below_the_total_is_the_ordinary_funded_case(self) -> None:
        """**Only the ceiling is checked, and deliberately.**

        Notes:
            Requiring the share to equal the total would refuse exactly the
            arrangement the field exists for: the département pays its part and
            the household the rest.
        """
        bill = Bill(
            **a_bill(
                recipient={
                    "kind": "public",
                    "name": "Conseil départemental de Paris",
                    "address": ADDRESS,
                    "siren": "130025265",
                    "share_ttc": "1.00",
                }
            )
        )

        assert bill.amount_due() < bill.total_ttc
