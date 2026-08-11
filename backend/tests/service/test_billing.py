from __future__ import annotations

# Standard library imports
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.billing.bill import Bill
from models.billing.bill_recipient import BillRecipient
from models.billing.billing_run import BillingRun
from models.companies.company import Company
from models.configuration.billing_config import BillingConfig
from models.enums import (
    BillingPeriodicity,
    BillingRunStatus,
    BillStatus,
    InterventionStatus,
    QuoteStatus,
    ServiceCategory,
)
from models.geo.postal_address import PostalAddress
from models.people.customer import Customer
from models.planning.intervention import Intervention
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from models.schemas.requests.billing.billing_settings_request import (
    BillingSettingsRequest,
)
from models.settings.billing_settings import BillingSettings
from service.billing.billings import BillingService
from service.billing.exceptions import (
    MTBillAlreadyIssued,
    MTBillDocumentStorageUnavailable,
    MTBillDocumentUnavailable,
    MTBillingPeriodInFuture,
    MTBillingRunNotFound,
    MTBillNothingToBill,
    MTBillTransitionNotAllowed,
)
from service.utils.invoice_renderer import InvoiceRenderer
from storage.repositories.billing.bill import BillRepository
from storage.repositories.billing.billing_run import BillingRunRepository
from storage.repositories.billing.billing_settings import (
    BillingSettingsRepository,
)
from storage.repositories.companies.company import CompanyRepository
from storage.repositories.people.customer import CustomerRepository
from storage.repositories.planning.intervention import InterventionRepository
from storage.repositories.quoting.quote import QuoteRepository
from storage.s3.s3_storage import S3Storage

COMPANY = "company-1"
CUSTOMER = "customer-1"
ADDRESS = PostalAddress(
    street="1 rue des Lilas",
    postal_code="75011",
    city="Paris",
    country="France",
)
# A window in the past: a period still running cannot be billed.
MARCH = (date(2026, 3, 1), date(2026, 3, 31))
# A day inside it. Generation is asked for a *day* and resolves the window from
# the customer's own periodicity, so no test can hand in a window that
# disagrees with what the customer is billed on.
IN_MARCH = date(2026, 3, 9)


def a_quote_line(
    service_date: date = date(2026, 3, 9),
    line_id: str = "line-1",
    name: str = "Aide à la toilette",
    total_ht: str = "63.82",
    priced: bool = True,
) -> QuoteLine:
    """Build one sold service.

    Args:
        service_date (date): The day it is delivered.
        line_id (str): Its identifier.
        name (str): What the service is.
        total_ht (str): The line total excluding tax.
        priced (bool): Whether the line carries its amounts.

    Returns:
        QuoteLine: The line.
    """
    money: Dict[str, Any] = {}
    if priced:
        vat = (Decimal(total_ht) * Decimal("0.055")).quantize(Decimal("0.01"))
        money = {
            "hourly_rate_ht": Decimal("31.91"),
            "total_ht": Decimal(total_ht),
            "vat_amount": vat,
            "total_ttc": Decimal(total_ht) + vat,
        }
    return QuoteLine(
        id=line_id,
        name=name,
        intervention_type_id="type-1",
        service_category=ServiceCategory.NECESSITY,
        service_date=service_date,
        earliest_start=time(8, 0),
        latest_end=time(18, 0),
        duration_minutes=120,
        **money,
    )


def a_quote(lines: List[QuoteLine], **overrides: Any) -> Quote:
    """Build an accepted quote.

    Args:
        lines (List[QuoteLine]): The services sold.
        **overrides: Fields to replace.

    Returns:
        Quote: The quote.
    """
    payload: Dict[str, Any] = {
        "company_id": COMPANY,
        "reference": "D-2648",
        "customer_id": CUSTOMER,
        "status": QuoteStatus.ACCEPTED,
        "lines": lines,
    }
    payload.update(overrides)
    return Quote(**payload)


def a_visit(line_id: str = "line-1", day: date = date(2026, 3, 9)) -> Intervention:
    """Build the scheduled visit that delivered a line.

    Args:
        line_id (str): The quote line it delivers.
        day (date): The day it happened.

    Returns:
        Intervention: The visit.
    """
    return Intervention(
        id=f"visit-{line_id}",
        company_id=COMPANY,
        planning_run_id="run-1",
        name="Aide à la toilette",
        intervention_type_id="type-1",
        quote_line_id=line_id,
        hca_id="hca-1",
        hca_full_name="Amina Benali",
        customer_id=CUSTOMER,
        day=day,
        start_time=time(9, 0),
        end_time=time(11, 0),
        address=ADDRESS,
        status=InterventionStatus.PLANNED,
    )


def a_customer(
    periodicity: Optional[BillingPeriodicity] = None,
    customer_id: str = CUSTOMER,
) -> Customer:
    """Build the customer being billed.

    Args:
        periodicity (Optional[BillingPeriodicity]): Their own invoicing
            granularity, or ``None`` to follow the agency's.
        customer_id (str): Their identifier.

    Returns:
        Customer: The customer.
    """
    return Customer(
        id=customer_id,
        first_name="Jeanne",
        last_name="Vincent",
        phone_number="+33612345678",
        email="jeanne.vincent@example.com",
        address=ADDRESS,
        billing_periodicity=periodicity,
    )


def an_agency() -> Company:
    """Build the agency issuing invoices.

    Returns:
        Company: The agency.

    Notes:
        The registration and VAT numbers are not decoration. A structured
        invoice is routed on the first and refused without the second, so an
        agency fixture missing them cannot produce a document at all — which is
        the behaviour under test elsewhere, and noise here.
    """
    return Company(
        id=COMPANY,
        name="Aide et Présence Paris",
        legal_form="SARL",
        registration_number="12345678900019",
        vat_number="FR12345678900",
        iban="FR7630006000011234567890189",
        bic="AGRIFRPP",
        address=ADDRESS,
    )


def a_service(
    quotes: Optional[List[Quote]] = None,
    visits: Optional[List[Intervention]] = None,
    already_billed: bool = False,
    documents: Optional[MagicMock] = None,
    customer: Optional[Customer] = None,
    overrides: Optional[List[BillingPeriodicity]] = None,
) -> BillingService:
    """Build a service over doubles, with one customer and one agency.

    Args:
        quotes (Optional[List[Quote]]): What the quote repository returns.
        visits (Optional[List[Intervention]]): What the planner placed.
        already_billed (bool): Whether the period is billed already.
        documents (Optional[MagicMock]): The object store double, or ``None``
            to build a working one.
        customer (Optional[Customer]): The customer being billed, when their
            own invoicing granularity is what the test is about.
        overrides (Optional[List[BillingPeriodicity]]): The granularities other
            customers have asked for, which is what widens a run's search.

    Returns:
        BillingService: The service under test.

    Notes:
        Doubles are ``MagicMock(spec=...)`` so a method that stops existing
        breaks the test rather than silently answering a mock — the house
        pattern for service tests.
    """
    bills = MagicMock(spec=BillRepository)
    bills.find_overlapping = AsyncMock(
        return_value=[_a_stored_bill()] if already_billed else []
    )
    bills.next_number = AsyncMock(return_value=(1, "FA-2026-000001"))
    bills.create = AsyncMock(
        side_effect=lambda bill: bill.model_copy(update={"id": "bill-1"})
    )
    bills.get = AsyncMock(return_value=None)
    bills.set_status = AsyncMock(return_value=None)
    bills.mark_sent = AsyncMock(return_value=None)

    runs = MagicMock(spec=BillingRunRepository)
    runs.create = AsyncMock(
        side_effect=lambda run: run.model_copy(update={"id": "run-1"})
    )
    runs.get = AsyncMock(return_value=None)
    runs.mark_running = AsyncMock(return_value=None)
    runs.mark_finished = AsyncMock(
        side_effect=lambda run_id, status, finished_at, **kwargs: BillingRun(
            id=run_id,
            company_id=COMPANY,
            status=status,
            reference_date=date(2026, 4, 1),
            periodicity=BillingPeriodicity.MONTHLY,
            period_start=MARCH[0],
            period_end=MARCH[1],
            bill_ids=kwargs.get("bill_ids") or [],
            failed_customer_ids=kwargs.get("failed_customer_ids") or [],
            requested_at=datetime.now(UTC),
        )
    )

    settings = MagicMock(spec=BillingSettingsRepository)
    settings.get = AsyncMock(return_value=BillingSettings())
    settings.seed = AsyncMock(return_value=BillingSettings())
    settings.update = AsyncMock(side_effect=lambda updated: updated)

    quote_repository = MagicMock(spec=QuoteRepository)
    quote_repository.list_schedulable = AsyncMock(return_value=quotes or [])

    interventions = MagicMock(spec=InterventionRepository)
    interventions.list_for_customer = AsyncMock(return_value=visits or [])

    customers = MagicMock(spec=CustomerRepository)
    customers.get = AsyncMock(return_value=customer or a_customer())
    customers.list_billing_periodicities = AsyncMock(return_value=overrides or [])

    companies = MagicMock(spec=CompanyRepository)
    companies.get = AsyncMock(return_value=an_agency())

    store = documents
    if store is None:
        store = MagicMock(spec=S3Storage)
        store.upload_invoice = AsyncMock(return_value="invoices/company-1/a.pdf")
        store.fetch_invoice = AsyncMock(return_value=b"%PDF-1.4 stored")
        store.fetch_logo = AsyncMock(return_value=None)

    return BillingService(
        bills=bills,
        runs=runs,
        settings=settings,
        quotes=quote_repository,
        interventions=interventions,
        customers=customers,
        companies=companies,
        config=BillingConfig(),
        documents=store,
        renderer=InvoiceRenderer(),
    )


class TestTheTimeProRata:
    """Tests for requirement 3, which is the whole of ``collect_lines``."""

    @pytest.mark.asyncio
    async def test_only_the_lines_inside_the_window_are_charged(self) -> None:
        """**The pro-rata is a date filter and nothing else.**

        Notes:
            A quote line carries one ``service_date``, so no line can straddle a
            period boundary. "Only the part inside the window is billed"
            therefore needs no fractional arithmetic — and adding some later
            would re-price an invoice that is legally required not to move.
        """
        quote = a_quote(
            [
                a_quote_line(date(2026, 2, 25), "before"),
                a_quote_line(date(2026, 3, 9), "inside"),
                a_quote_line(date(2026, 4, 2), "after"),
            ]
        )
        service = a_service(quotes=[quote])

        charges = await service.collect_lines(COMPANY, CUSTOMER, *MARCH)

        assert [line.quote_line_id for line in charges] == ["inside"]

    @pytest.mark.asyncio
    async def test_both_bounds_of_the_window_are_charged(self) -> None:
        """The window contains both of its own ends.

        Notes:
            An exclusive end would drop the 31st of every month — a day of care
            nobody is charged for and nobody notices.
        """
        quote = a_quote(
            [
                a_quote_line(date(2026, 3, 1), "first-day"),
                a_quote_line(date(2026, 3, 31), "last-day"),
            ]
        )
        service = a_service(quotes=[quote])

        charges = await service.collect_lines(COMPANY, CUSTOMER, *MARCH)

        assert len(charges) == 2

    @pytest.mark.asyncio
    async def test_a_quote_spanning_months_is_split_without_loss(self) -> None:
        """**Four monthly invoices sum to the quote.**

        Notes:
            The property requirement 3 is really asking for: the customer is
            charged the whole of what they agreed to, once, spread across the
            periods the work fell in.
        """
        lines = [
            a_quote_line(date(2026, month, 9), f"line-{month}")
            for month in (3, 4, 5, 6)
        ]
        quote = a_quote(lines)
        service = a_service(quotes=[quote])

        billed = Decimal("0.00")
        for month, last in ((3, 31), (4, 30), (5, 31), (6, 30)):
            charges = await service.collect_lines(
                COMPANY, CUSTOMER, date(2026, month, 1), date(2026, month, last)
            )
            assert len(charges) == 1
            billed += charges[0].total_ht

        assert billed == sum(line.total_ht or Decimal("0.00") for line in lines)

    @pytest.mark.asyncio
    async def test_an_interrupted_quote_stops_being_billed(self) -> None:
        """An arrangement ends on the day it stopped being delivered.

        Notes:
            ``interrupted_on`` is inclusive, so the interruption day itself is
            still delivered and still billed. Read through
            ``Quote.effective_lines`` rather than re-implemented, so the
            invoice and the planner cannot disagree about what is still owed.
        """
        quote = a_quote(
            [
                a_quote_line(date(2026, 3, 9), "kept"),
                a_quote_line(date(2026, 3, 15), "on-the-day"),
                a_quote_line(date(2026, 3, 20), "dropped"),
            ],
            issued_on=date(2026, 3, 1),
            interrupted_on=date(2026, 3, 15),
        )
        service = a_service(quotes=[quote])

        charges = await service.collect_lines(COMPANY, CUSTOMER, *MARCH)

        assert [line.quote_line_id for line in charges] == ["kept", "on-the-day"]

    @pytest.mark.asyncio
    async def test_another_customer_s_work_is_not_charged(self) -> None:
        """One customer's invoice never carries another's care."""
        mine = a_quote([a_quote_line(line_id="mine")])
        theirs = a_quote([a_quote_line(line_id="theirs")], customer_id="customer-2")
        service = a_service(quotes=[mine, theirs])

        charges = await service.collect_lines(COMPANY, CUSTOMER, *MARCH)

        assert [line.quote_line_id for line in charges] == ["mine"]


class TestTheMoneyIsCopied:
    """Tests that an invoice reprints identically for ever."""

    @pytest.mark.asyncio
    async def test_the_amounts_come_from_the_quote_line(self) -> None:
        """**Copied, never recomputed.**

        Notes:
            A rate that moved in the catalogue after the quote was written must
            not reach an invoice for work sold before it moved. The service
            never calls the pricing code at all — this asserts the figures are
            the line's own, to the cent.
        """
        line = a_quote_line(total_ht="99.99")
        service = a_service(quotes=[a_quote([line])])

        charge = (await service.collect_lines(COMPANY, CUSTOMER, *MARCH))[0]

        assert charge.total_ht == line.total_ht
        assert charge.vat_amount == line.vat_amount
        assert charge.total_ttc == line.total_ttc
        assert charge.hourly_rate_ht == line.hourly_rate_ht

    @pytest.mark.asyncio
    async def test_the_vat_rate_is_stored_on_the_charge(self) -> None:
        """So a reprint after a statutory change still shows what was charged."""
        service = a_service(quotes=[a_quote([a_quote_line()])])

        charge = (await service.collect_lines(COMPANY, CUSTOMER, *MARCH))[0]

        assert charge.vat_rate == ServiceCategory.NECESSITY.vat_rate()

    @pytest.mark.asyncio
    async def test_an_unpriced_line_is_dropped_and_reported(self) -> None:
        """Charging nothing for delivered care is a loss nobody notices.

        Notes:
            A bill line requires its money, so an unpriced quote line cannot be
            carried onto an invoice as a zero. It is left off and logged at
            error, which is the only way anybody finds out.
        """
        quote = a_quote(
            [
                a_quote_line(line_id="priced"),
                a_quote_line(line_id="unpriced", priced=False),
            ]
        )
        service = a_service(quotes=[quote])

        charges = await service.collect_lines(COMPANY, CUSTOMER, *MARCH)

        assert [line.quote_line_id for line in charges] == ["priced"]


class TestTheDeliveredVisit:
    """Tests for the hours and the assistant printed beside a charge."""

    @pytest.mark.asyncio
    async def test_a_placed_visit_enriches_its_charge(self) -> None:
        """An invoice says who came and when, not merely what was sold."""
        service = a_service(quotes=[a_quote([a_quote_line()])], visits=[a_visit()])

        charge = (await service.collect_lines(COMPANY, CUSTOMER, *MARCH))[0]

        assert charge.was_delivered() is True
        assert charge.hca_full_name == "Amina Benali"
        assert charge.start_time == time(9, 0)
        assert charge.intervention_id == "visit-line-1"

    @pytest.mark.asyncio
    async def test_work_the_planner_never_placed_is_still_billed(self) -> None:
        """**Dropping it would forgive money the agency earned.**

        Notes:
            The visit was sold and delivered whether or not a planning run ever
            saw it. The charge keeps its sold date and prints no assistant.
        """
        service = a_service(quotes=[a_quote([a_quote_line()])], visits=[])

        charge = (await service.collect_lines(COMPANY, CUSTOMER, *MARCH))[0]

        assert charge.was_delivered() is False
        assert charge.total_ht == Decimal("63.82")

    @pytest.mark.asyncio
    async def test_the_visit_is_matched_by_its_quote_line(self) -> None:
        """Two services on one day must not swap their assistants."""
        quote = a_quote(
            [
                a_quote_line(line_id="morning", name="Toilette"),
                a_quote_line(line_id="afternoon", name="Courses"),
            ]
        )
        service = a_service(quotes=[quote], visits=[a_visit("afternoon")])

        charges = {
            line.quote_line_id: line
            for line in await service.collect_lines(COMPANY, CUSTOMER, *MARCH)
        }

        assert charges["afternoon"].was_delivered() is True
        assert charges["morning"].was_delivered() is False


class TestIssuingAnInvoice:
    """Tests for what generating one actually writes."""

    @pytest.mark.asyncio
    async def test_an_invoice_is_written_waiting_for_validation(self) -> None:
        """**A generation run sends nothing.**

        Notes:
            Every document is rendered and stored, and every invoice waits for
            a manager. Nothing reaches a customer until somebody approves it.
        """
        service = a_service(quotes=[a_quote([a_quote_line()])])

        issued = await service.generate_for_customer(COMPANY, CUSTOMER, IN_MARCH)

        assert issued is not None
        assert issued.status is BillStatus.TO_BE_VALIDATED
        assert issued.sent_at is None
        assert issued.document_key == "invoices/company-1/a.pdf"

    @pytest.mark.asyncio
    async def test_the_document_is_stored_before_the_record(self) -> None:
        """A row pointing at a document that does not exist is a burnt number."""
        service = a_service(quotes=[a_quote([a_quote_line()])])

        await service.generate_for_customer(COMPANY, CUSTOMER, IN_MARCH)

        service.documents.upload_invoice.assert_awaited_once()
        stored = service.bills.create.await_args.args[0]
        assert stored.document_key == "invoices/company-1/a.pdf"

    @pytest.mark.asyncio
    async def test_the_totals_are_the_sum_of_the_charges(self) -> None:
        """What the customer adds up against."""
        quote = a_quote(
            [
                a_quote_line(line_id="a", total_ht="63.82"),
                a_quote_line(line_id="b", total_ht="31.91"),
            ]
        )
        service = a_service(quotes=[quote])

        issued = await service.generate_for_customer(COMPANY, CUSTOMER, IN_MARCH)

        assert issued is not None
        assert issued.total_ht == Decimal("95.73")
        assert issued.total_ttc == issued.total_ht + issued.total_vat

    @pytest.mark.asyncio
    async def test_the_customer_s_name_and_address_are_snapshotted(self) -> None:
        """A customer who moves must not rewrite last quarter's invoice."""
        service = a_service(quotes=[a_quote([a_quote_line()])])

        issued = await service.generate_for_customer(COMPANY, CUSTOMER, IN_MARCH)

        assert issued is not None
        assert issued.customer_full_name == "Jeanne Vincent"
        assert issued.customer_address.city == "Paris"

    @pytest.mark.asyncio
    async def test_the_due_date_follows_the_configured_terms(self) -> None:
        """The date the document prints is the date the record holds."""
        service = a_service(quotes=[a_quote([a_quote_line()])])
        service.settings.get = AsyncMock(
            return_value=BillingSettings(payment_terms_days=45)
        )

        issued = await service.generate_for_customer(COMPANY, CUSTOMER, IN_MARCH)

        assert issued is not None
        assert (issued.due_on - issued.issued_on).days == 45

    @pytest.mark.asyncio
    async def test_an_empty_period_issues_no_invoice(self) -> None:
        """**A number is never burnt on a document charging nothing.**

        Notes:
            A gap in the series in all but name. A customer with no visits in a
            period simply has nothing to pay.
        """
        service = a_service(quotes=[])

        assert await service.generate_for_customer(COMPANY, CUSTOMER, IN_MARCH) is None
        service.bills.next_number.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_period_already_billed_is_skipped(self) -> None:
        """A re-run is a reported no-op, not a second invoice."""
        service = a_service(quotes=[a_quote([a_quote_line()])], already_billed=True)

        assert await service.generate_for_customer(COMPANY, CUSTOMER, IN_MARCH) is None
        service.bills.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_deployment_with_no_store_refuses_before_numbering(
        self,
    ) -> None:
        """**Checked before a number is allocated, never after.**

        Notes:
            An invoice whose document could not be stored would leave a burnt
            number behind, and the series cannot explain a gap.
        """
        service = a_service(quotes=[a_quote([a_quote_line()])])
        service.documents = None

        with pytest.raises(MTBillDocumentStorageUnavailable):
            await service.generate_for_customer(COMPANY, CUSTOMER, IN_MARCH)


class TestRequestingARun:
    """Tests for asking a period to be billed."""

    @pytest.mark.asyncio
    async def test_a_run_is_recorded_before_it_is_queued(self) -> None:
        """So the identifier a caller polls is real with no broker."""
        service = a_service()

        run = await service.request_run(COMPANY, date(2026, 3, 15), "manager-1")

        assert run.id == "run-1"
        assert run.status is BillingRunStatus.PENDING
        assert (run.period_start, run.period_end) == MARCH

    @pytest.mark.asyncio
    async def test_a_period_still_running_is_refused(self) -> None:
        """**Care that has not happened cannot be invoiced.**

        Notes:
            Refused rather than billed early, because an invoice covering a
            month still in progress would need correcting — and a correction
            means a credit note, not an edit.
        """
        service = a_service()

        with pytest.raises(MTBillingPeriodInFuture):
            await service.request_run(COMPANY, datetime.now(UTC).date(), "manager-1")

    @pytest.mark.asyncio
    async def test_a_partial_run_names_the_customers_it_could_not_bill(
        self,
    ) -> None:
        """**The only thing that makes a partial month actionable.**

        Notes:
            One bad customer costs one invoice, not the month. A count would
            leave somebody comparing two lists by hand to find who was missed.
        """
        quote = a_quote([a_quote_line()])
        other = a_quote([a_quote_line(line_id="other")], customer_id="customer-2")
        service = a_service(quotes=[quote, other])
        service.runs.get = AsyncMock(
            return_value=BillingRun(
                id="run-1",
                company_id=COMPANY,
                reference_date=IN_MARCH,
                periodicity=BillingPeriodicity.MONTHLY,
                period_start=MARCH[0],
                period_end=MARCH[1],
                requested_at=datetime.now(UTC),
            )
        )
        service.customers.get = AsyncMock(
            side_effect=lambda customer_id: (
                None if customer_id == "customer-2" else a_customer()
            )
        )

        finished = await service.execute_run("run-1")

        assert finished.status is BillingRunStatus.PARTIAL
        assert finished.failed_customer_ids == ["customer-2"]
        assert finished.bill_count() == 1

    @pytest.mark.asyncio
    async def test_an_unknown_run_is_refused(self) -> None:
        """A worker handed an identifier for nothing gives up loudly."""
        service = a_service()

        with pytest.raises(MTBillingRunNotFound):
            await service.execute_run("no-such-run")


class TestTheLifecycle:
    """Tests for moving an invoice through its commercial statuses."""

    @pytest.mark.asyncio
    async def test_a_manager_may_step_forward(self) -> None:
        """Validation is what sends the invoice."""
        service = a_service()
        stored = _a_stored_bill()
        service.bills.get = AsyncMock(return_value=stored)
        service.bills.set_status = AsyncMock(
            return_value=stored.model_copy(update={"status": BillStatus.ACCEPTED})
        )

        moved = await service.set_status("bill-1", BillStatus.ACCEPTED, "manager-1")

        assert moved.status is BillStatus.ACCEPTED

    @pytest.mark.asyncio
    async def test_a_skip_is_refused(self) -> None:
        """**Decided against the stored status, never against the screen's.**

        Notes:
            A row rendered a minute ago may have moved since, and a client
            cannot be trusted to have re-read it. Skipping to paid would erase
            the record of the invoice ever having been approved or sent.
        """
        service = a_service()
        service.bills.get = AsyncMock(return_value=_a_stored_bill())

        with pytest.raises(MTBillTransitionNotAllowed):
            await service.set_status("bill-1", BillStatus.PAID, "manager-1")

    @pytest.mark.asyncio
    async def test_a_step_back_corrects_a_misclick(self) -> None:
        """A manager who marked the wrong row needs the way back."""
        service = a_service()
        accepted = _a_stored_bill(status=BillStatus.ACCEPTED)
        service.bills.get = AsyncMock(return_value=accepted)
        service.bills.set_status = AsyncMock(
            return_value=accepted.model_copy(
                update={"status": BillStatus.TO_BE_VALIDATED}
            )
        )

        moved = await service.set_status(
            "bill-1", BillStatus.TO_BE_VALIDATED, "manager-1"
        )

        assert moved.status is BillStatus.TO_BE_VALIDATED


class TestDownloadingTheDocument:
    """Tests for serving a stored invoice back."""

    @pytest.mark.asyncio
    async def test_the_filename_comes_from_the_invoice_number(self) -> None:
        """**Never from anything a client sends.**

        Notes:
            A filename taken from a request is how a download endpoint starts
            writing files somebody else chose the name of.
        """
        service = a_service()
        service.bills.get = AsyncMock(return_value=_a_stored_bill())

        payload, filename = await service.document("bill-1")

        assert payload.startswith(b"%PDF-")
        assert filename == "FA-2026-000001.pdf"

    @pytest.mark.asyncio
    async def test_an_unreadable_document_is_reported_as_unavailable(
        self,
    ) -> None:
        """The record is real; the store is what did not answer."""
        service = a_service()
        service.bills.get = AsyncMock(return_value=_a_stored_bill())
        service.documents.fetch_invoice = AsyncMock(return_value=None)

        with pytest.raises(MTBillDocumentUnavailable):
            await service.document("bill-1")


class TestBillingOneCustomer:
    """Tests for the path where a caller names a single customer."""

    @pytest.mark.asyncio
    async def test_an_already_billed_period_is_an_error_here(self) -> None:
        """**Unlike a run, which passes over it silently.**

        Notes:
            A run over everybody skips both an empty period and a billed one,
            because most customers have no work in most weeks. A caller who
            named one customer asked a question and is owed an answer.
        """
        service = a_service(quotes=[a_quote([a_quote_line()])], already_billed=True)

        with pytest.raises(MTBillAlreadyIssued):
            await service.bill_one(COMPANY, CUSTOMER, date(2026, 3, 15), "manager-1")

    @pytest.mark.asyncio
    async def test_an_empty_period_is_an_error_here_too(self) -> None:
        """Asking to bill somebody who owes nothing is worth being told."""
        service = a_service(quotes=[])

        with pytest.raises(MTBillNothingToBill):
            await service.bill_one(COMPANY, CUSTOMER, date(2026, 3, 15), "manager-1")


class TestACustomersOwnGranularity:
    """Tests for a customer invoiced on something other than the agency rule."""

    @pytest.mark.asyncio
    async def test_a_weekly_customer_is_billed_over_their_week(self) -> None:
        """**The override decides the window, and only the window.**

        Notes:
            The agency bills monthly and this customer weekly, so the same run
            and the same day produce a seven-day invoice. What it charges is
            still copied from the quote, which is the line between a
            granularity and a price: one decides which days appear, the other
            is never recomputed at all.
        """
        service = a_service(
            quotes=[a_quote([a_quote_line(IN_MARCH)])],
            customer=a_customer(BillingPeriodicity.WEEKLY),
        )

        issued = await service.generate_for_customer(COMPANY, CUSTOMER, IN_MARCH)

        assert issued is not None
        assert issued.periodicity is BillingPeriodicity.WEEKLY
        assert (issued.period_start, issued.period_end) == (
            date(2026, 3, 9),
            date(2026, 3, 15),
        )

    @pytest.mark.asyncio
    async def test_a_customer_whose_period_is_still_running_is_passed_over(
        self,
    ) -> None:
        """**The run's window finishing says nothing about theirs.**

        Notes:
            A customer billed yearly has an open year while the agency closes a
            month. Billing them now would invoice care that has not happened, so
            they are skipped with a warning and picked up once their year ends —
            not counted as a failure, because nothing went wrong.
        """
        service = a_service(
            quotes=[a_quote([a_quote_line()])],
            customer=a_customer(BillingPeriodicity.YEARLY),
        )

        assert await service.generate_for_customer(COMPANY, CUSTOMER, IN_MARCH) is None
        service.bills.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_days_already_covered_are_not_billed_a_second_time(self) -> None:
        """**What a changed granularity would otherwise cost a customer.**

        Notes:
            Billed for a week and then moved to monthly, they would be charged
            twice for those days: two windows that differ, so the unique index
            sees nothing, over care delivered once. The overlap check is what
            catches it, and it catches a plain re-run in the same breath.
        """
        service = a_service(quotes=[a_quote([a_quote_line()])], already_billed=True)

        assert await service.generate_for_customer(COMPANY, CUSTOMER, IN_MARCH) is None
        service.bills.next_number.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_run_looks_beyond_its_own_window_when_customers_differ(
        self,
    ) -> None:
        """**A yearly customer has work a July run must still find.**

        Notes:
            Discovery spans every periodicity in use; each customer is then
            billed over their own window alone, so a wider search never widens
            what anybody is charged. With nobody overridden the span is exactly
            the agency's own window and the run does the work it always did.
        """
        service = a_service(overrides=[BillingPeriodicity.YEARLY])

        assert await service.spanned_window(IN_MARCH) == (
            date(2026, 1, 1),
            date(2026, 12, 31),
        )

    @pytest.mark.asyncio
    async def test_a_run_spans_only_the_agency_window_when_nobody_differs(
        self,
    ) -> None:
        """The common case costs nothing: one periodicity, one window."""
        service = a_service()

        assert await service.spanned_window(IN_MARCH) == MARCH

    @pytest.mark.asyncio
    async def test_billing_one_customer_refuses_their_open_period(self) -> None:
        """**The refusal has to name the period they would be charged for.**

        Notes:
            The agency's March is finished and this customer's year is not.
            Reporting the agency's window here would tell a manager the period
            is closed while the server refuses it as open.
        """
        service = a_service(
            quotes=[a_quote([a_quote_line()])],
            customer=a_customer(BillingPeriodicity.YEARLY),
        )

        with pytest.raises(MTBillingPeriodInFuture) as raised:
            await service.bill_one(COMPANY, CUSTOMER, IN_MARCH, "manager-1")

        assert "2026-01-01..2026-12-31" in str(raised.value)

    @pytest.mark.asyncio
    async def test_the_window_a_screen_previews_is_the_customers_own(self) -> None:
        """So a manager is not shown a period the customer will never get."""
        service = a_service(customer=a_customer(BillingPeriodicity.WEEKLY))

        assert await service.window_for(IN_MARCH) == MARCH
        assert await service.window_for(IN_MARCH, CUSTOMER) == (
            date(2026, 3, 9),
            date(2026, 3, 15),
        )


class TestTheInvoicingRules:
    """Tests for the settings the documents are printed under."""

    @pytest.mark.asyncio
    async def test_the_rules_are_seeded_on_first_read(self) -> None:
        """An invoice without payment terms is non-conforming."""
        service = a_service()
        service.settings.get = AsyncMock(return_value=None)

        assert (await service.current_settings()).payment_terms_days == 30
        service.settings.seed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_change_records_who_made_it(self) -> None:
        """A change to what customers are told has a name attached."""
        service = a_service()

        updated = await service.update_settings(
            BillingSettingsRequest(periodicity=BillingPeriodicity.WEEKLY),
            actor="manager-1",
        )

        assert updated.periodicity is BillingPeriodicity.WEEKLY
        assert updated.updated_by == "manager-1"

    @pytest.mark.asyncio
    async def test_the_window_comes_from_the_stored_rule(self) -> None:
        """A caller never resolves a period under a rule nobody configured."""
        service = a_service()
        service.settings.get = AsyncMock(
            return_value=BillingSettings(periodicity=BillingPeriodicity.WEEKLY)
        )

        assert await service.window_for(date(2026, 8, 13)) == (
            date(2026, 8, 10),
            date(2026, 8, 16),
        )


def _a_stored_bill(status: BillStatus = BillStatus.TO_BE_VALIDATED) -> Bill:
    """Build an invoice as it comes back from the store.

    Args:
        status (BillStatus): The status it is stored in.

    Returns:
        Bill: The invoice.
    """
    line = a_quote_line()
    return Bill(
        id="bill-1",
        company_id=COMPANY,
        customer_id=CUSTOMER,
        number="FA-2026-000001",
        sequence=1,
        sequence_year=2026,
        periodicity=BillingPeriodicity.MONTHLY,
        period_start=MARCH[0],
        period_end=MARCH[1],
        issued_on=date(2026, 4, 1),
        due_on=date(2026, 5, 1),
        status=status,
        customer_full_name="Jeanne Vincent",
        customer_address=ADDRESS,
        recipient=BillRecipient(name="Jeanne Vincent", address=ADDRESS),
        lines=[
            {
                "quote_line_id": "line-1",
                "name": line.name,
                "service_category": line.service_category,
                "service_date": line.service_date,
                "duration_minutes": line.duration_minutes,
                "hourly_rate_ht": line.hourly_rate_ht,
                "total_ht": line.total_ht,
                "vat_rate": Decimal("0.055"),
                "vat_amount": line.vat_amount,
                "total_ttc": line.total_ttc,
            }
        ],
        total_ht=line.total_ht or Decimal("0.00"),
        total_vat=line.vat_amount or Decimal("0.00"),
        total_ttc=line.total_ttc or Decimal("0.00"),
        document_key="invoices/company-1/a.pdf",
    )
