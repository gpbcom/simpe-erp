from __future__ import annotations

# Standard library imports
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.billing.bill import Bill
from models.enums import (
    BillingPeriodicity,
    Language,
    QuoteStatus,
    RegistrationStatus,
)
from models.people.customer import Customer
from models.planning.intervention.intervention import Intervention
from models.quoting.quote import Quote
from models.schemas.requests.customers.customer_profile_update_request import (
    CustomerProfileUpdateRequest,
)
from service.customers.exceptions import MTCustomerNotFound
from service.customers.portal import CustomerPortalService


def _customer(status: RegistrationStatus = RegistrationStatus.ACTIVE) -> Customer:
    """Build the household the portal belongs to.

    Args:
        status (RegistrationStatus): Their registration status.

    Returns:
        Customer: The household.
    """
    return Customer(
        id="customer-1",
        first_name="Marie",
        last_name="Durand",
        phone_number="+33612345678",
        email="marie.durand@example.com",
        address={
            "street": "12 rue de Rivoli",
            "postal_code": "75004",
            "city": "Paris",
            "latitude": 48.8558,
            "longitude": 2.3588,
        },
        registration_status=status,
    )


def _visit(customer_id: str = "customer-1") -> Intervention:
    """Build a scheduled visit.

    Args:
        customer_id (str): The household it is for.

    Returns:
        Intervention: The visit.
    """
    return Intervention(
        company_id="company-1",
        id="intervention-1",
        name="Toilette",
        intervention_type_id="type-1",
        quote_line_id="line-1",
        hca_id="hca-1",
        hca_full_name="Luc Martin",
        customer_id=customer_id,
        customer_full_name="Marie Durand",
        address={
            "street": "12 rue de Rivoli",
            "postal_code": "75004",
            "city": "Paris",
            "latitude": 48.8558,
            "longitude": 2.3588,
        },
        day=date(2026, 9, 14),
        start_time="09:00",
        end_time="10:00",
    )


def _quote(status: QuoteStatus = QuoteStatus.ACCEPTED) -> Quote:
    """Build the quote a visit was sold on.

    Args:
        status (QuoteStatus): Where it sits in its lifecycle.

    Returns:
        Quote: The quote.
    """
    return Quote(
        company_id="company-1",
        id="quote-1",
        reference="Q-2026-0001",
        customer_id="customer-1",
        status=status,
    )


def _bill(customer_id: str = "customer-1") -> Bill:
    """Build an issued invoice.

    Args:
        customer_id (str): The household it is addressed to.

    Returns:
        Bill: The invoice.
    """
    return Bill(
        company_id="company-1",
        id="bill-1",
        customer_id=customer_id,
        number="F-2026-0042",
        sequence=42,
        sequence_year=2026,
        periodicity=BillingPeriodicity.MONTHLY,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        issued_on=date(2026, 4, 1),
        due_on=date(2026, 5, 1),
        customer_full_name="Marie Durand",
        customer_address={
            "street": "12 rue de Rivoli",
            "postal_code": "75004",
            "city": "Paris",
            "latitude": 48.8558,
            "longitude": 2.3588,
        },
        recipient={
            "name": "Marie Durand",
            "address": {
                "street": "12 rue de Rivoli",
                "postal_code": "75004",
                "city": "Paris",
                "latitude": 48.8558,
                "longitude": 2.3588,
            },
        },
        # Zero, and it has to be: ``Bill`` cross-validates its totals against
        # its lines, and these tests are about who may read the invoice rather
        # than about what it says.
        total_ht=Decimal("0.00"),
        total_vat=Decimal("0.00"),
        total_ttc=Decimal("0.00"),
    )


@pytest.fixture
def customers() -> AsyncMock:
    """Return a stand-in customer service.

    Returns:
        AsyncMock: The service double.
    """
    service = AsyncMock()
    service.get.return_value = _customer()
    service.update.side_effect = lambda customer_id, customer: customer
    service.quotes_for.return_value = [_quote()]
    return service


@pytest.fixture
def interventions() -> AsyncMock:
    """Return a stand-in visit service.

    Returns:
        AsyncMock: The service double, cancelling to a surviving quote.
    """
    service = AsyncMock()
    service.delete.return_value = _quote()
    return service


@pytest.fixture
def quotes() -> AsyncMock:
    """Return a stand-in quote service.

    Returns:
        AsyncMock: The service double.
    """
    service = AsyncMock()
    service.get.return_value = _quote()
    service.get_by_line.return_value = _quote()
    service.reschedule_line.return_value = _quote()
    return service


@pytest.fixture
def quote_store() -> AsyncMock:
    """Return a stand-in quote repository.

    Returns:
        AsyncMock: The repository double, holding an accepted quote.
    """
    repository = AsyncMock()
    repository.get.return_value = _quote()
    repository.set_status.return_value = _quote(QuoteStatus.PENDING_VALIDATION)
    return repository


@pytest.fixture
def intervention_store() -> AsyncMock:
    """Return a stand-in visit repository.

    Returns:
        AsyncMock: The repository double.
    """
    repository = AsyncMock()
    repository.get.return_value = _visit()
    repository.list_for_customer.return_value = [_visit()]
    return repository


@pytest.fixture
def service(
    customers: AsyncMock,
    interventions: AsyncMock,
    quotes: AsyncMock,
    quote_store: AsyncMock,
    intervention_store: AsyncMock,
) -> CustomerPortalService:
    """Return a portal service over stand-in collaborators.

    Args:
        customers (AsyncMock): The customer service double.
        interventions (AsyncMock): The visit service double.
        quotes (AsyncMock): The quote service double.
        quote_store (AsyncMock): The quote repository double.
        intervention_store (AsyncMock): The visit repository double.

    Returns:
        CustomerPortalService: The service under test.
    """
    bills = AsyncMock()
    bills.list.return_value = []
    bills.get.return_value = _bill()
    bills.document.return_value = (b"%PDF-1.4 invoice", "F-2026-0042.pdf")
    documents = AsyncMock()
    documents.document.return_value = (b"%PDF-1.4 quote", "Q-2026-0001.pdf")
    return CustomerPortalService(
        customers=customers,
        interventions=interventions,
        quotes=quotes,
        quote_store=quote_store,
        intervention_store=intervention_store,
        bills=bills,
        documents=documents,
    )


class TestPortalReads:
    """Tests for what a household may see."""

    async def test_the_profile_is_their_own_record(
        self, service: CustomerPortalService, customers: AsyncMock
    ) -> None:
        """The household comes from the credential, not from a parameter."""
        profile = await service.profile("customer-1")

        assert profile.id == "customer-1"
        customers.get.assert_awaited_once_with("customer-1")

    async def test_the_planning_is_scoped_in_the_statement(
        self, service: CustomerPortalService, intervention_store: AsyncMock
    ) -> None:
        """**Scoped by the query, not filtered afterwards.**

        Notes:
            A page narrowed after the fact has already read visits belonging to
            other households — every one of which carries a name, an address and
            a care schedule.
        """
        await service.planning("customer-1", date(2026, 9, 1), date(2026, 9, 30))

        intervention_store.list_for_customer.assert_awaited_once_with(
            "customer-1", date(2026, 9, 1), date(2026, 9, 30)
        )

    async def test_the_quotes_are_unfiltered(
        self, service: CustomerPortalService, customers: AsyncMock
    ) -> None:
        """Including refused and expired ones.

        Notes:
            A household asking "what did you quote me in March" is asking about
            the history. A list narrowed to what is live answers a different
            question without saying so.
        """
        await service.quotes_for("customer-1")

        customers.quotes_for.assert_awaited_once_with("customer-1")


class TestPortalOwnership:
    """Tests for the row-level rule behind the whole space."""

    async def test_another_households_visit_is_not_found(
        self, service: CustomerPortalService, intervention_store: AsyncMock
    ) -> None:
        """**404, not 403, and the distinction is the point.**

        Notes:
            Telling "no such visit" apart from "not yours" would let somebody
            walk the identifier space and learn when the agency visits their
            neighbours. The same reasoning the assistant portfolio already
            applies to customers.
        """
        intervention_store.get.return_value = _visit(customer_id="customer-2")

        with pytest.raises(MTCustomerNotFound):
            await service.cancel_visit("customer-1", "intervention-1")

    async def test_an_absent_visit_answers_the_same_way(
        self, service: CustomerPortalService, intervention_store: AsyncMock
    ) -> None:
        """The two cases are deliberately indistinguishable."""
        intervention_store.get.return_value = None

        with pytest.raises(MTCustomerNotFound):
            await service.cancel_visit("customer-1", "intervention-1")

    async def test_nothing_is_cancelled_for_another_household(
        self,
        service: CustomerPortalService,
        intervention_store: AsyncMock,
        interventions: AsyncMock,
    ) -> None:
        """The refusal happens before anything is written."""
        intervention_store.get.return_value = _visit(customer_id="customer-2")

        with pytest.raises(MTCustomerNotFound):
            await service.reschedule_visit(
                "customer-1", "intervention-1", date(2026, 9, 15), 540, 720
            )

        interventions.delete.assert_not_awaited()


class TestBackToValidation:
    """Tests for what a household's change does to the agreement."""

    async def test_cancelling_sends_the_quote_back(
        self, service: CustomerPortalService, quote_store: AsyncMock
    ) -> None:
        """**The requirement, in one assertion.**

        Notes:
            The household has changed what the agency agreed to deliver, so the
            agreement is no longer current and a manager has to see it again.
            Until they do, nothing on that quote is scheduled — the planner
            builds requirements only from accepted quotes.
        """
        await service.cancel_visit("customer-1", "intervention-1")

        quote_store.set_status.assert_awaited_once_with(
            "quote-1", QuoteStatus.PENDING_VALIDATION
        )

    async def test_rescheduling_sends_the_quote_back(
        self, service: CustomerPortalService, quote_store: AsyncMock
    ) -> None:
        """Moving work changes the agreement as much as removing it does."""
        await service.reschedule_visit(
            "customer-1", "intervention-1", date(2026, 9, 15), 540, 720
        )

        quote_store.set_status.assert_awaited_once_with(
            "quote-1", QuoteStatus.PENDING_VALIDATION
        )

    async def test_the_underlying_reschedule_is_reused_unchanged(
        self, service: CustomerPortalService, quotes: AsyncMock
    ) -> None:
        """**A composition, not a reimplementation.**

        Notes:
            ``QuoteService.reschedule_line`` already moves the line and
            reprices, and it deliberately leaves the status alone because it was
            written for a manager. The portal calls it as it is and adds the
            status move on top, so the two callers differ in exactly one place.
        """
        await service.reschedule_visit(
            "customer-1", "intervention-1", date(2026, 9, 15), 540, 720
        )

        quotes.reschedule_line.assert_awaited_once_with(
            quote_id="quote-1",
            quote_line_id="line-1",
            day=date(2026, 9, 15),
            start_minute=540,
            end_minute=720,
        )

    async def test_a_quote_already_awaiting_validation_is_left_alone(
        self, service: CustomerPortalService, quote_store: AsyncMock
    ) -> None:
        """The move is idempotent.

        Notes:
            Two changes in a row must not write two identical audit lines, and a
            quote already in the queue is already where this puts it.
        """
        quote_store.get.return_value = _quote(QuoteStatus.PENDING_VALIDATION)

        await service.cancel_visit("customer-1", "intervention-1")

        quote_store.set_status.assert_not_awaited()

    async def test_cancelling_the_last_visit_leaves_nothing_to_validate(
        self,
        service: CustomerPortalService,
        interventions: AsyncMock,
        quote_store: AsyncMock,
    ) -> None:
        """A quote whose last line goes is deleted with it.

        Notes:
            There is then no quote to send back, which is why the return is
            optional. Setting a status on a deleted row would be a 500 at the
            end of an operation that succeeded.
        """
        interventions.delete.return_value = None

        assert await service.cancel_visit("customer-1", "intervention-1") is None

        quote_store.set_status.assert_not_awaited()

    async def test_the_quote_is_re_read_after_the_status_moves(
        self, service: CustomerPortalService, quote_store: AsyncMock
    ) -> None:
        """The caller is handed the quote as it now is.

        Notes:
            The repricing and the status move are two writes. Returning the
            value from the first would hand the screen a quote still marked
            accepted, and the household would see no sign that anything needs
            approving.
        """
        quote_store.get.side_effect = [
            _quote(QuoteStatus.ACCEPTED),
            _quote(QuoteStatus.PENDING_VALIDATION),
        ]

        answered = await service.cancel_visit("customer-1", "intervention-1")

        assert answered is not None
        assert answered.status is QuoteStatus.PENDING_VALIDATION


class TestProfileEditing:
    """Tests for what a household may change about themselves."""

    async def test_the_contact_block_is_replaced(
        self, service: CustomerPortalService, customers: AsyncMock
    ) -> None:
        """The ordinary case works."""
        updated = await service.update_profile(
            "customer-1",
            CustomerProfileUpdateRequest(
                first_name="Marie-Claire",
                last_name="Durand",
                phone_number="+33699999999",
                email="mc.durand@example.com",
                address={
                    "street": "5 rue de Turenne",
                    "postal_code": "75003",
                    "city": "Paris",
                    "latitude": 48.86,
                    "longitude": 2.36,
                },
            ),
        )

        assert updated.first_name == "Marie-Claire"
        assert updated.address.street == "5 rue de Turenne"

    async def test_the_status_survives_the_edit(
        self, service: CustomerPortalService, customers: AsyncMock
    ) -> None:
        """**A household cannot promote themselves by saving their address.**

        Notes:
            The request model has no field for the status, and this is the
            second gate: the stored record is the base and only the payload's
            own fields replace anything. A prospect who edited their telephone
            number must still be a prospect afterwards — being active is what
            puts their work into the next planning run.
        """
        customers.get.return_value = _customer(RegistrationStatus.PROSPECT)

        updated = await service.update_profile(
            "customer-1",
            CustomerProfileUpdateRequest(
                first_name="Marie",
                last_name="Durand",
                phone_number="+33699999999",
                email="marie.durand@example.com",
                address={
                    "street": "12 rue de Rivoli",
                    "postal_code": "75004",
                    "city": "Paris",
                    "latitude": 48.8558,
                    "longitude": 2.3588,
                },
            ),
        )

        assert updated.registration_status is RegistrationStatus.PROSPECT


class TestPortalDocuments:
    """Tests for the row-level rule on the two download buttons."""

    async def test_the_invoices_are_narrowed_in_the_query(
        self, service: CustomerPortalService
    ) -> None:
        """**Narrowed by a filter, not filtered afterwards.**

        Notes:
            A page of the agency's invoices narrowed after the fact has already
            read other households' figures — and an invoice carries a name, an
            address and what a family pays for their care.
        """
        await service.bills_for("customer-1", "company-1")

        applied = service.bills.list.await_args.kwargs["bill_filter"]
        assert applied.customer_id == "customer-1"

    async def test_another_households_invoice_is_not_found(
        self, service: CustomerPortalService
    ) -> None:
        """404 for both "not yours" and "no such invoice".

        Notes:
            The check lives here rather than on the billing service, because
            that service answers a manager who is entitled to every invoice.
            The narrowing belongs to the caller.
        """
        service.bills.get.return_value = _bill(customer_id="customer-2")

        with pytest.raises(MTCustomerNotFound):
            await service.bill_document("customer-1", "bill-1")

        service.bills.document.assert_not_awaited()

    async def test_their_own_invoice_is_served(
        self, service: CustomerPortalService
    ) -> None:
        """The ordinary case works."""
        payload, filename = await service.bill_document("customer-1", "bill-1")

        assert payload.startswith(b"%PDF-")
        assert filename == "F-2026-0042.pdf"

    async def test_another_households_quote_is_not_found(
        self, service: CustomerPortalService, quotes: AsyncMock
    ) -> None:
        """The same rule on the other document."""
        quotes.get.return_value = _quote().model_copy(
            update={"customer_id": "customer-2"}
        )

        with pytest.raises(MTCustomerNotFound):
            await service.quote_document("customer-1", "quote-1", Language.FR)

        service.documents.document.assert_not_awaited()

    async def test_a_quote_is_rendered_in_the_households_language(
        self, service: CustomerPortalService
    ) -> None:
        """The same offer, addressed to two different readers."""
        await service.quote_document("customer-1", "quote-1", Language.EN)

        assert service.documents.document.await_args.kwargs["language"] is Language.EN
