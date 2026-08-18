from __future__ import annotations

# Standard library imports
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Dict, List

# Third-party imports
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.billing.bill import Bill
from models.billing.bill_line import BillLine
from models.billing.billing_run import BillingRun
from models.enums import (
    BillingPeriodicity,
    BillingRunStatus,
    BillStatus,
    OperationNature,
    RecipientKind,
    ServiceCategory,
)
from models.people.customer import Customer
from models.schemas.requests.billing.bill_filter import BillFilter
from models.settings.billing_settings import BillingSettings
from storage.repositories.billing.bill import BillRepository
from storage.repositories.billing.billing_run import BillingRunRepository
from storage.repositories.billing.billing_settings import (
    BillingSettingsRepository,
)
from storage.repositories.people.customer import CustomerRepository
from tests.annotations import ModelInput

COMPANY = "company-1"
ADDRESS: Dict[str, ModelInput] = {
    "street": "12 rue de Rivoli",
    "postal_code": "75004",
    "city": "Paris",
    "country": "France",
}


def a_charge(
    service_date: date = date(2026, 3, 9), **overrides: ModelInput
) -> BillLine:
    """Build one priced charge.

    Args:
        service_date (date): The day the service was sold for.
        **overrides: Fields to replace on the default charge.

    Returns:
        BillLine: A charge a bill accepts.
    """
    payload: Dict[str, ModelInput] = {
        "quote_line_id": "quote-line-1",
        "name": "Aide à la toilette",
        "service_category": ServiceCategory.NECESSITY,
        "service_date": service_date,
        "duration_minutes": 120,
        "hourly_rate_ht": Decimal("31.91"),
        "total_ht": Decimal("63.82"),
        "vat_rate": Decimal("0.055"),
        "vat_amount": Decimal("3.51"),
        "total_ttc": Decimal("67.33"),
    }
    payload.update(overrides)
    return BillLine(**payload)


def a_bill(customer_id: str, **overrides: ModelInput) -> Bill:
    """Build a March invoice for a customer.

    Args:
        customer_id (str): The customer it is addressed to.
        **overrides: Fields to replace on the default invoice.

    Returns:
        Bill: An invoice ready to store.
    """
    lines: List[BillLine] = overrides.pop("lines", [a_charge()])
    payload: Dict[str, ModelInput] = {
        "company_id": COMPANY,
        "customer_id": customer_id,
        "number": "FA-2026-000001",
        "sequence": 1,
        "sequence_year": 2026,
        "periodicity": BillingPeriodicity.MONTHLY,
        "period_start": date(2026, 3, 1),
        "period_end": date(2026, 3, 31),
        "issued_on": date(2026, 4, 1),
        "due_on": date(2026, 5, 1),
        "customer_full_name": "Marie Durand",
        "customer_address": ADDRESS,
        "recipient": {"name": "Marie Durand", "address": ADDRESS},
        "lines": lines,
        "total_ht": sum((line.total_ht for line in lines), Decimal("0.00")),
        "total_vat": sum((line.vat_amount for line in lines), Decimal("0.00")),
        "total_ttc": sum((line.total_ttc for line in lines), Decimal("0.00")),
        "document_key": "invoices/company-1/abc.pdf",
    }
    payload.update(overrides)
    return Bill(**payload)


async def a_customer(session: AsyncSession, customer: Customer) -> str:
    """Store a customer and return their identifier.

    Args:
        session (AsyncSession): The open session.
        customer (Customer): The customer to store.

    Returns:
        str: The stored customer's identifier.

    Notes:
        Bills carry a restricting foreign key to ``customers``, so a test that
        invented an identifier would fail on the constraint rather than on the
        thing it meant to check.
    """
    stored = await CustomerRepository(session).create(customer)
    assert stored.id is not None
    return stored.id


class TestBillNumbering:
    """Tests for the legal invoice series."""

    @pytest.mark.asyncio
    async def test_the_first_number_of_a_year_is_one(
        self, session: AsyncSession
    ) -> None:
        """A series counts documents issued, so it starts at one."""
        sequence, number = await BillRepository(session).next_number(COMPANY, 2026)
        assert sequence == 1
        assert number == "FA-2026-000001"

    @pytest.mark.asyncio
    async def test_the_series_is_gapless(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """Each allocation follows the last with nothing skipped.

        Notes:
            French invoicing requires an unbroken, chronological sequence per
            issuer. A gap is not a cosmetic problem — it is the thing an
            inspection asks about.
        """
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        for expected in (1, 2, 3):
            sequence, number = await repository.next_number(COMPANY, 2026)
            assert sequence == expected
            await repository.create(
                a_bill(
                    customer_id,
                    number=number,
                    sequence=sequence,
                    period_start=date(2026, expected, 1),
                    period_end=date(2026, expected, 28),
                    lines=[a_charge(service_date=date(2026, expected, 9))],
                )
            )

    @pytest.mark.asyncio
    async def test_two_agencies_keep_separate_series(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """One agency's invoices never advance another's numbering."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        await repository.create(a_bill(customer_id))

        sequence, _ = await repository.next_number("company-2", 2026)
        assert sequence == 1

    @pytest.mark.asyncio
    async def test_the_series_restarts_each_year(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """The year in the number is what makes the restart unambiguous."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        await repository.create(a_bill(customer_id))

        sequence, number = await repository.next_number(COMPANY, 2027)
        assert (sequence, number) == (1, "FA-2027-000001")

    @pytest.mark.asyncio
    async def test_a_reused_number_is_refused(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """Two documents under one number is the failure the index prevents."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        await repository.create(a_bill(customer_id))

        with pytest.raises(IntegrityError):
            await repository.create(
                a_bill(
                    customer_id,
                    sequence=2,
                    period_start=date(2026, 4, 1),
                    period_end=date(2026, 4, 30),
                    lines=[a_charge(service_date=date(2026, 4, 9))],
                )
            )

    @pytest.mark.asyncio
    async def test_a_reused_series_position_is_refused(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """Two runs allocating one position must fail, not leave a gap."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        await repository.create(a_bill(customer_id))

        with pytest.raises(IntegrityError):
            await repository.create(
                a_bill(
                    customer_id,
                    number="FA-2026-999999",
                    sequence=1,
                    period_start=date(2026, 4, 1),
                    period_end=date(2026, 4, 30),
                    lines=[a_charge(service_date=date(2026, 4, 9))],
                )
            )


class TestBillIdempotency:
    """Tests for the guard against billing a customer twice."""

    @pytest.mark.asyncio
    async def test_a_period_reports_itself_as_unbilled_first(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """Nothing has been billed before anything is written."""
        customer_id = await a_customer(session, customer)
        assert (
            await BillRepository(session).find_overlapping(
                customer_id, date(2026, 3, 1), date(2026, 3, 31)
            )
            == []
        )

    @pytest.mark.asyncio
    async def test_a_billed_period_is_reported(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """The friendly half of the guard, so a re-run is a reported no-op."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        await repository.create(a_bill(customer_id))

        found = await repository.find_overlapping(
            customer_id, date(2026, 3, 1), date(2026, 3, 31)
        )

        assert [bill.number for bill in found] == ["FA-2026-000001"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("window", "expected"),
        [
            pytest.param(
                (date(2026, 3, 2), date(2026, 3, 8)),
                ["FA-2026-000001"],
                id="A week inside a billed month",
            ),
            pytest.param(
                (date(2026, 2, 23), date(2026, 3, 1)),
                ["FA-2026-000001"],
                id="A week straddling the first day",
            ),
            pytest.param(
                (date(2026, 1, 1), date(2026, 12, 31)),
                ["FA-2026-000001"],
                id="A year containing a billed month",
            ),
            pytest.param(
                (date(2026, 2, 1), date(2026, 2, 28)),
                [],
                id="Invalid - the month before touches nothing",
            ),
            pytest.param(
                (date(2026, 4, 1), date(2026, 4, 30)),
                [],
                id="Invalid - the month after touches nothing",
            ),
        ],
    )
    async def test_a_window_overlapping_a_billed_one_is_reported(
        self,
        session: AsyncSession,
        customer: Customer,
        window: tuple[date, date],
        expected: list[str],
    ) -> None:
        """**What an exact-window check could never catch.**

        Notes:
            A customer moved from weekly to monthly billing mid-period would
            otherwise be charged twice for the same days: two windows that
            differ, so the unique index sees nothing, over care delivered once.
            Containment either way round, a partial overlap either way round and
            an exact match are all one expression, which is why there are no
            cases in the query and five here.
        """
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        await repository.create(a_bill(customer_id))

        found = await repository.find_overlapping(customer_id, *window)

        assert [bill.number for bill in found] == expected

    @pytest.mark.asyncio
    async def test_a_second_invoice_for_one_period_is_refused(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """**The guarantee, as opposed to the check.**

        Notes:
            Two runs waking together both pass ``find_overlapping`` and both
            attempt the insert. This index is what stops the customer receiving
            two invoices for one month. The service catches the failure and
            re-reads the winner.
        """
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        await repository.create(a_bill(customer_id))

        with pytest.raises(IntegrityError):
            await repository.create(
                a_bill(customer_id, number="FA-2026-000002", sequence=2)
            )

    @pytest.mark.asyncio
    async def test_a_different_period_is_billable(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """The guard is about one window, not about the customer."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        await repository.create(a_bill(customer_id))

        april = await repository.create(
            a_bill(
                customer_id,
                number="FA-2026-000002",
                sequence=2,
                period_start=date(2026, 4, 1),
                period_end=date(2026, 4, 30),
                lines=[a_charge(service_date=date(2026, 4, 9))],
            )
        )
        assert april.id is not None


class TestBillReads:
    """Tests for how invoices come back."""

    @pytest.mark.asyncio
    async def test_an_invoice_round_trips_whole(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """Everything printed on the document survives the store."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        stored = await repository.create(a_bill(customer_id))

        assert stored.id is not None
        read = await repository.get(stored.id)
        assert read is not None
        assert read.number == "FA-2026-000001"
        assert read.customer_full_name == "Marie Durand"
        assert read.customer_address.city == "Paris"
        assert read.total_ttc == Decimal("67.33")
        assert read.lines[0].vat_rate == Decimal("0.055")
        assert read.status is BillStatus.TO_BE_VALIDATED

    @pytest.mark.asyncio
    async def test_charges_come_back_in_printed_order(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """An invoice reprinted in another order is a call nobody can settle."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        lines = [
            a_charge(service_date=date(2026, 3, 20), name="Courses"),
            a_charge(service_date=date(2026, 3, 2), name="Toilette"),
        ]
        stored = await repository.create(a_bill(customer_id, lines=lines))

        assert stored.id is not None
        read = await repository.get(stored.id)
        assert read is not None
        assert [line.name for line in read.lines] == ["Courses", "Toilette"]

    @pytest.mark.asyncio
    async def test_a_number_is_found_however_it_is_typed(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """A customer reading it over the telephone still finds their invoice."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        await repository.create(a_bill(customer_id))

        found = await repository.get_by_number("  fa-2026-000001 ")
        assert found is not None

    @pytest.mark.asyncio
    async def test_an_unknown_invoice_reports_nothing(
        self, session: AsyncSession
    ) -> None:
        """A missing invoice is ``None``, never an exception from here."""
        repository = BillRepository(session)
        assert await repository.get("no-such-bill") is None
        assert await repository.get_by_number("FA-2026-999999") is None

    @pytest.mark.asyncio
    async def test_a_run_reports_the_invoices_it_wrote(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """A run is reported on whole, so this is unpaginated by design."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        await repository.create(a_bill(customer_id, billing_run_id="run-1"))

        assert len(await repository.list_for_run("run-1")) == 1
        assert await repository.list_for_run("run-2") == []


class TestBillFiltering:
    """Tests for what narrows the invoice list."""

    @pytest.mark.asyncio
    async def test_a_filter_cannot_escape_the_caller_s_scope(
        self,
        session: AsyncSession,
        customer: Customer,
        customer_kwargs: Dict[str, ModelInput],
    ) -> None:
        """**The scope wins, always.**

        Notes:
            An invoice list is the one screen where a filter that could widen
            its own scope would show one customer's money to somebody entitled
            to another's.
        """
        repository = BillRepository(session)
        mine = await a_customer(session, customer)
        other_kwargs = dict(customer_kwargs)
        other_kwargs["email"] = "other@example.com"
        theirs = await a_customer(session, Customer(**other_kwargs))
        await repository.create(a_bill(mine))
        await repository.create(a_bill(theirs, number="FA-2026-000002", sequence=2))

        escaped = await repository.list(
            customer_id=mine, bill_filter=BillFilter(customer_id=theirs)
        )
        assert [bill.customer_id for bill in escaped] == [mine]

    @pytest.mark.asyncio
    async def test_the_sent_filter_reads_the_timestamp(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """ "Awaiting payment" and "actually sent" are different questions.

        Notes:
            A bill a manager pushed forward by hand while the mail server was
            down is awaited but was never sent, and somebody chasing what has
            gone out needs the second answer.
        """
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        stored = await repository.create(
            a_bill(
                customer_id,
                status=BillStatus.WAITING_PAYMENT,
                document_key="invoices/company-1/abc.pdf",
            )
        )
        assert stored.id is not None

        assert await repository.list(bill_filter=BillFilter(is_sent=True)) == []
        unsent = await repository.list(bill_filter=BillFilter(is_sent=False))
        assert len(unsent) == 1

        await repository.mark_sent(stored.id, datetime.now(UTC))
        assert len(await repository.list(bill_filter=BillFilter(is_sent=True))) == 1

    @pytest.mark.asyncio
    async def test_the_period_bounds_narrow_by_the_window_billed(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """ "Show me March" means the care delivered in March."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        await repository.create(a_bill(customer_id))
        await repository.create(
            a_bill(
                customer_id,
                number="FA-2026-000002",
                sequence=2,
                period_start=date(2026, 4, 1),
                period_end=date(2026, 4, 30),
                lines=[a_charge(service_date=date(2026, 4, 9))],
            )
        )

        march = await repository.list(
            bill_filter=BillFilter(
                period_start=date(2026, 3, 1), period_end=date(2026, 3, 31)
            )
        )
        assert [bill.number for bill in march] == ["FA-2026-000001"]

    @pytest.mark.asyncio
    async def test_a_number_fragment_narrows_the_list(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """The search box takes what somebody has in front of them."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        await repository.create(a_bill(customer_id))

        assert len(await repository.list(bill_filter=BillFilter(search="000001"))) == 1
        assert await repository.list(bill_filter=BillFilter(search="999")) == []

    @pytest.mark.asyncio
    async def test_counting_matches_listing(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """The count and the page are built from one statement."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        await repository.create(a_bill(customer_id))

        applied = BillFilter(status=BillStatus.TO_BE_VALIDATED)
        assert await repository.count(bill_filter=applied) == len(
            await repository.list(bill_filter=applied)
        )


class TestBillWriters:
    """Tests for the narrow writers."""

    @pytest.mark.asyncio
    async def test_attaching_a_document_changes_nothing_else(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """A narrow writer, so storing a document cannot change the amounts."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        stored = await repository.create(a_bill(customer_id, document_key=None))
        assert stored.id is not None

        updated = await repository.attach_document(
            stored.id, "invoices/company-1/def.pdf"
        )
        assert updated is not None
        assert updated.document_key == "invoices/company-1/def.pdf"
        assert updated.total_ttc == stored.total_ttc

    @pytest.mark.asyncio
    async def test_approval_stamps_who_and_when(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """ "Who agreed to send this?" is a question the record must answer."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        stored = await repository.create(a_bill(customer_id))
        assert stored.id is not None
        moment = datetime.now(UTC)

        approved = await repository.set_status(
            stored.id, BillStatus.ACCEPTED, actor="manager-1", moment=moment
        )
        assert approved is not None
        assert approved.validated_by == "manager-1"
        assert approved.validated_at is not None

    @pytest.mark.asyncio
    async def test_stepping_back_does_not_erase_the_approval(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """An invoice that was approved once was approved once.

        Notes:
            Clearing the stamp on a step back would be rewriting the audit
            trail rather than correcting a status.
        """
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        stored = await repository.create(a_bill(customer_id))
        assert stored.id is not None
        moment = datetime.now(UTC)

        await repository.set_status(
            stored.id, BillStatus.ACCEPTED, actor="manager-1", moment=moment
        )
        stepped_back = await repository.set_status(
            stored.id, BillStatus.TO_BE_VALIDATED, actor="manager-1"
        )
        assert stepped_back is not None
        assert stepped_back.validated_by == "manager-1"

    @pytest.mark.asyncio
    async def test_settlement_records_its_day(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """When an invoice was paid is what reconciles the bank statement."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        stored = await repository.create(a_bill(customer_id))
        assert stored.id is not None
        moment = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)

        paid = await repository.set_status(
            stored.id, BillStatus.PAID, actor="manager-1", moment=moment
        )
        assert paid is not None
        assert paid.paid_on == date(2026, 5, 4)

    @pytest.mark.asyncio
    async def test_a_writer_reports_a_missing_invoice(
        self, session: AsyncSession
    ) -> None:
        """A writer aimed at nothing answers ``None`` rather than raising."""
        repository = BillRepository(session)
        assert await repository.attach_document("no-such-bill", "k") is None
        assert await repository.set_status("no-such-bill", BillStatus.PAID) is None
        assert await repository.mark_sent("no-such-bill", datetime.now(UTC)) is None


class TestBillingRunRepository:
    """Tests for the record of a request to bill a period."""

    @pytest.mark.asyncio
    async def test_a_run_is_recorded_before_it_is_queued(
        self, session: AsyncSession
    ) -> None:
        """The identifier a caller polls must be real even with no broker."""
        stored = await BillingRunRepository(session).create(
            BillingRun(
                company_id=COMPANY,
                requested_by="manager-1",
                reference_date=date(2026, 4, 1),
                periodicity=BillingPeriodicity.MONTHLY,
                period_start=date(2026, 3, 1),
                period_end=date(2026, 3, 31),
                requested_at=datetime.now(UTC),
            )
        )
        assert stored.id is not None
        assert stored.status is BillingRunStatus.PENDING

    @pytest.mark.asyncio
    async def test_a_run_records_what_it_managed_to_do(
        self, session: AsyncSession
    ) -> None:
        """A partial month is only actionable if it names who went unbilled."""
        repository = BillingRunRepository(session)
        stored = await repository.create(
            BillingRun(
                company_id=COMPANY,
                reference_date=date(2026, 4, 1),
                periodicity=BillingPeriodicity.MONTHLY,
                period_start=date(2026, 3, 1),
                period_end=date(2026, 3, 31),
                requested_at=datetime.now(UTC),
            )
        )
        assert stored.id is not None

        await repository.mark_running(stored.id, datetime.now(UTC))
        finished = await repository.mark_finished(
            stored.id,
            BillingRunStatus.PARTIAL,
            datetime.now(UTC),
            bill_ids=["bill-1", "bill-2"],
            failed_customer_ids=["customer-9"],
        )
        assert finished is not None
        assert finished.bill_count() == 2
        assert finished.failed_customer_ids == ["customer-9"]
        assert finished.is_terminal() is True

    @pytest.mark.asyncio
    async def test_an_empty_outcome_is_recorded_as_empty(
        self, session: AsyncSession
    ) -> None:
        """ "Billed nobody and failed nobody" is a real answer.

        Notes:
            A period with no deliverable work. Left null, it would be
            indistinguishable from a run that never reported at all.
        """
        repository = BillingRunRepository(session)
        stored = await repository.create(
            BillingRun(
                company_id=COMPANY,
                reference_date=date(2026, 4, 1),
                periodicity=BillingPeriodicity.MONTHLY,
                period_start=date(2026, 3, 1),
                period_end=date(2026, 3, 31),
                requested_at=datetime.now(UTC),
            )
        )
        assert stored.id is not None

        finished = await repository.mark_finished(
            stored.id, BillingRunStatus.SUCCEEDED, datetime.now(UTC)
        )
        assert finished is not None
        assert finished.bill_ids == []
        assert finished.failed_customer_ids == []

    @pytest.mark.asyncio
    async def test_a_missing_run_is_reported_not_raised(
        self, session: AsyncSession
    ) -> None:
        """A worker handed an unknown identifier logs and gives up."""
        repository = BillingRunRepository(session)
        assert await repository.get("no-such-run") is None
        assert await repository.mark_running("no-such-run", datetime.now(UTC)) is None


class TestBillingSettingsRepository:
    """Tests for the single row of invoicing rules."""

    @pytest.mark.asyncio
    async def test_nothing_is_stored_until_it_is_seeded(
        self, session: AsyncSession
    ) -> None:
        """The row is created on first read, not by the migration."""
        assert await BillingSettingsRepository(session).get() is None

    @pytest.mark.asyncio
    async def test_seeding_stores_the_configured_rules(
        self, session: AsyncSession
    ) -> None:
        """What ``app.yaml`` says is what the first read writes."""
        repository = BillingSettingsRepository(session)
        seeded = await repository.seed(
            BillingSettings(periodicity=BillingPeriodicity.WEEKLY)
        )
        assert seeded.periodicity is BillingPeriodicity.WEEKLY
        assert seeded.id == BillingSettings.SINGLETON_ID

    @pytest.mark.asyncio
    async def test_seeding_twice_keeps_the_first_answer(
        self, session: AsyncSession
    ) -> None:
        """Two requests arriving together must not collide on the key.

        Notes:
            The re-read before writing is what turns the loser of that race
            into a caller that simply finds the row already there.
        """
        repository = BillingSettingsRepository(session)
        await repository.seed(BillingSettings(periodicity=BillingPeriodicity.WEEKLY))
        again = await repository.seed(
            BillingSettings(periodicity=BillingPeriodicity.YEARLY)
        )
        assert again.periodicity is BillingPeriodicity.WEEKLY

    @pytest.mark.asyncio
    async def test_updating_records_who_changed_the_terms(
        self, session: AsyncSession
    ) -> None:
        """An edit to what customers are told has a name attached."""
        repository = BillingSettingsRepository(session)
        await repository.seed(BillingSettings())

        updated = await repository.update(
            BillingSettings(payment_terms_days=45, updated_by="manager-1")
        )
        assert updated is not None
        assert updated.payment_terms_days == 45
        assert updated.updated_by == "manager-1"

    @pytest.mark.asyncio
    async def test_updating_before_seeding_is_refused(
        self, session: AsyncSession
    ) -> None:
        """Quietly creating the row would hide an ordering mistake."""
        assert (
            await BillingSettingsRepository(session).update(BillingSettings()) is None
        )


class TestTheRecipientSurvivesStorage:
    """Tests for the party an invoice was billed to, read back."""

    @pytest.mark.asyncio
    async def test_a_household_round_trips(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """The ordinary case: the household pays for its own care."""
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)

        stored = await repository.create(a_bill(customer_id))
        read = await repository.get(stored.id)

        assert read is not None
        assert read.recipient.kind is RecipientKind.INDIVIDUAL
        assert read.recipient.name == "Marie Durand"
        assert read.recipient.siren is None
        assert read.operation_nature is OperationNature.SERVICES

    @pytest.mark.asyncio
    async def test_a_funded_payer_round_trips_whole(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """**Every identifier, or the invoice cannot be routed on re-read.**

        Notes:
            The SIREN is what a platform delivers on and the service code is
            what a public body routes on internally. A column dropped from the
            mapper would surface as an invoice nobody can deliver, months after
            it was written.
        """
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        payer = {
            "kind": "public",
            "name": "Conseil départemental de Paris",
            "address": ADDRESS,
            "siren": "130025265",
            "vat_number": "FR12345678900",
            "service_code": "APA",
        }

        stored = await repository.create(a_bill(customer_id, recipient=payer))
        read = await repository.get(stored.id)

        assert read is not None
        assert read.recipient.kind is RecipientKind.PUBLIC
        assert read.recipient.siren == "130025265"
        assert read.recipient.vat_number == "FR12345678900"
        assert read.recipient.service_code == "APA"
        assert read.requires_electronic_invoice() is True

    @pytest.mark.asyncio
    async def test_the_billing_address_keeps_its_coordinate(
        self, session: AsyncSession, customer: Customer
    ) -> None:
        """**Which is why three columns nobody queries exist.**

        Notes:
            ``PostalAddress`` geocodes while it validates and skips the lookup
            only when a coordinate or a failure code is already set. Dropping
            them here would make every read of every invoice a blocking request
            to a geocoding service.
        """
        repository = BillRepository(session)
        customer_id = await a_customer(session, customer)
        placed = {**ADDRESS, "latitude": 48.8558, "longitude": 2.3588}

        stored = await repository.create(
            a_bill(
                customer_id,
                recipient={"name": "Marie Durand", "address": placed},
            )
        )
        read = await repository.get(stored.id)

        assert read is not None
        assert read.recipient.address.latitude == 48.8558
        assert read.recipient.address.longitude == 2.3588
