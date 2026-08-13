from __future__ import annotations

# Standard library imports
from typing import List, Optional
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.enums import BillingPeriodicity, QuoteStatus, RegistrationStatus
from models.people.customer import Customer
from models.quoting.quote import Quote
from models.schemas.requests.customers.customer_filter import CustomerFilter
from service.customers.customers import CustomerService
from service.customers.exceptions import (
    MTCustomerHasQuotes,
    MTCustomerNotFound,
    MTCustomerNotPromotable,
)


def _customer(
    customer_id: str = "customer-1",
    latitude: Optional[float] = 48.8566,
    longitude: Optional[float] = 2.3522,
    status: RegistrationStatus = RegistrationStatus.ACTIVE,
    periodicity: Optional[BillingPeriodicity] = None,
) -> Customer:
    """Build a customer.

    Args:
        customer_id (str): The identifier to assign.
        latitude (Optional[float]): The resolved latitude, if any.
        longitude (Optional[float]): The resolved longitude, if any.
        status (RegistrationStatus): Their registration status.
        periodicity (Optional[BillingPeriodicity]): Their own invoicing
            granularity, or ``None`` to follow the agency's.

    Returns:
        Customer: The customer.
    """
    return Customer(
        id=customer_id,
        first_name="Marie",
        last_name="Durand",
        phone_number="+33612345678",
        email=f"{customer_id}@example.com",
        address={
            "street": "12 rue de Rivoli",
            "postal_code": "75004",
            "city": "Paris",
            "latitude": latitude,
            "longitude": longitude,
        },
        registration_status=status,
        billing_periodicity=periodicity,
    )


def _quote() -> Quote:
    """Build a quote naming the customer.

    Returns:
        Quote: The quote.
    """
    return Quote(
        company_id="company-1",
        team_id="team-1",
        id="quote-1",
        reference="Q-2026-0001",
        customer_id="customer-1",
        status=QuoteStatus.ACCEPTED,
    )


@pytest.fixture
def customers() -> AsyncMock:
    """Return a stand-in customer repository.

    Returns:
        AsyncMock: The repository double, resolving any identifier.
    """
    repository = AsyncMock()
    repository.get.return_value = _customer()
    repository.create.side_effect = lambda customer: customer
    repository.update.side_effect = lambda customer: customer
    repository.set_status.return_value = _customer()
    repository.set_billing_periodicity.return_value = _customer()
    repository.list.return_value = [_customer()]
    repository.delete.return_value = True
    return repository


@pytest.fixture
def quotes() -> AsyncMock:
    """Return a stand-in quote repository holding nothing.

    Returns:
        AsyncMock: The repository double.
    """
    repository = AsyncMock()
    repository.list.return_value = []
    return repository


@pytest.fixture
def service(customers: AsyncMock, quotes: AsyncMock) -> CustomerService:
    """Return a customer service over stand-in repositories.

    Args:
        customers (AsyncMock): The customer repository double.
        quotes (AsyncMock): The quote repository double.

    Returns:
        CustomerService: The service under test.
    """
    return CustomerService(customers=customers, quotes=quotes)


class TestCustomerReads:
    """Tests for reading customers."""

    async def test_a_known_customer_is_returned(self, service: CustomerService) -> None:
        """The ordinary case works."""
        assert (await service.get("customer-1")).id == "customer-1"

    async def test_an_absent_customer_is_reported(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """A missing customer raises rather than returning ``None``.

        Notes:
            The endpoint turns this into a 404. Returning ``None`` would make
            every caller repeat the same check, and one of them would forget.
        """
        customers.get.return_value = None

        with pytest.raises(MTCustomerNotFound):
            await service.get("ghost")

    async def test_listing_passes_its_filters_through(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """A search and a status reach the repository."""
        await service.list(
            page=2, size=10, search="dur", status=RegistrationStatus.ACTIVE
        )

        customers.list.assert_awaited_once_with(
            page=2,
            size=10,
            search="dur",
            status=RegistrationStatus.ACTIVE,
            customer_filter=None,
            # No caller scope was given, so none is applied: `None` is every
            # household, which is what an unscoped call has always meant.
            customer_ids=None,
        )

    async def test_listing_passes_the_rich_filter_through(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """The customers screen's filter reaches the repository untouched.

        Notes:
            The service does not interpret the filter — it hands it on. The
            predicates live in one place, the repository's shared query
            builder, so a page and its total can never disagree about them.
        """
        applied = CustomerFilter(city="Paris", has_ongoing_arrangement=True)

        await service.list(customer_filter=applied)

        assert customers.list.await_args.kwargs["customer_filter"] is applied


class TestCustomerWrites:
    """Tests for creating and changing customers."""

    async def test_a_customer_is_created(self, service: CustomerService) -> None:
        """The ordinary case works."""
        assert (await service.create(_customer())).last_name == "Durand"

    async def test_an_ungeocoded_customer_is_still_accepted(
        self, service: CustomerService
    ) -> None:
        """A street the map does not know is still a customer.

        Notes:
            Refusing would make an unrecognised address block registration
            entirely. The consequence — their work cannot be planned — is
            reported at WARNING instead.
        """
        stored = await service.create(_customer(latitude=None, longitude=None))

        assert stored.address.is_geocoded() is False

    async def test_an_update_uses_the_path_identifier(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """A payload naming another customer edits the addressed one.

        Notes:
            Trusting the body would let a well-formed request rewrite somebody
            else's record — the sort of thing that reads as a data-entry
            mistake rather than the authorisation hole it is.
        """
        await service.update("customer-1", _customer(customer_id="customer-99"))

        assert customers.update.await_args.args[0].id == "customer-1"

    async def test_updating_an_absent_customer_is_reported(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """An update that matches nothing raises."""
        customers.update.side_effect = None
        customers.update.return_value = None

        with pytest.raises(MTCustomerNotFound):
            await service.update("ghost", _customer())

    async def test_a_customer_can_be_stopped(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """Stopping goes through the dedicated repository call."""
        customers.set_status.return_value = _customer(status=RegistrationStatus.STOPPED)

        stopped = await service.set_status("customer-1", RegistrationStatus.STOPPED)

        assert stopped.registration_status is RegistrationStatus.STOPPED

    async def test_stopping_an_absent_customer_is_reported(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """A status change that matches nothing raises."""
        customers.set_status.return_value = None

        with pytest.raises(MTCustomerNotFound):
            await service.set_status("ghost", RegistrationStatus.STOPPED)

    async def test_a_customer_can_be_given_their_own_granularity(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """The periodicity is a customer's field, written on its own."""
        customers.set_billing_periodicity.return_value = _customer(
            periodicity=BillingPeriodicity.WEEKLY
        )

        updated = await service.set_billing_periodicity(
            "customer-1", BillingPeriodicity.WEEKLY, actor="manager@example.fr"
        )

        assert updated.billing_periodicity is BillingPeriodicity.WEEKLY
        customers.set_billing_periodicity.assert_awaited_once_with(
            "customer-1", BillingPeriodicity.WEEKLY
        )

    async def test_a_customer_can_be_put_back_on_the_agency_rule(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """**Clearing has to reach the store as a clear.**

        Notes:
            Null is passed through rather than resolved to the agency's current
            rule. Writing the resolved value would look identical today and stop
            tracking the setting the moment a manager changed it.
        """
        await service.set_billing_periodicity(
            "customer-1", None, actor="manager@example.fr"
        )

        customers.set_billing_periodicity.assert_awaited_once_with("customer-1", None)

    async def test_setting_the_granularity_of_an_absent_customer_is_reported(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """A change that matches nothing raises rather than reporting success."""
        customers.set_billing_periodicity.return_value = None

        with pytest.raises(MTCustomerNotFound):
            await service.set_billing_periodicity(
                "ghost", BillingPeriodicity.WEEKLY, actor="manager@example.fr"
            )


class TestCustomerPromotion:
    """Tests for the act that puts a customer into the planning."""

    async def test_a_prospect_becomes_active(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """The ordinary case, and the only transition promotion allows."""
        customers.get.return_value = _customer(status=RegistrationStatus.PROSPECT)
        customers.set_status.return_value = _customer(status=RegistrationStatus.ACTIVE)

        promoted = await service.promote("customer-1")

        customers.set_status.assert_awaited_once_with(
            "customer-1", RegistrationStatus.ACTIVE
        )
        assert promoted.registration_status is RegistrationStatus.ACTIVE

    @pytest.mark.parametrize(
        "status",
        [
            pytest.param(RegistrationStatus.ACTIVE, id="already active"),
            pytest.param(RegistrationStatus.STOPPED, id="stopped"),
        ],
    )
    async def test_only_a_prospect_may_be_promoted(
        self,
        service: CustomerService,
        customers: AsyncMock,
        status: RegistrationStatus,
    ) -> None:
        """**Refused rather than shrugged off.**

        Args:
            service (CustomerService): The service under test.
            customers (AsyncMock): The repository double.
            status (RegistrationStatus): The status that cannot be promoted.

        Notes:
            An already-active customer is the case worth refusing: a control
            that silently succeeds when it did nothing is one somebody presses
            twice and then wonders which press took effect. Reinstating a
            *stopped* customer is a different decision with different
            consequences and goes through ``set_status``.
        """
        customers.get.return_value = _customer(status=status)

        with pytest.raises(MTCustomerNotPromotable):
            await service.promote("customer-1")

        customers.set_status.assert_not_awaited()

    async def test_promoting_an_absent_customer_is_reported(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """Nothing is written for somebody who is not there."""
        customers.get.return_value = None

        with pytest.raises(MTCustomerNotFound):
            await service.promote("no-such-customer")

        customers.set_status.assert_not_awaited()


class TestCustomerDeletion:
    """Tests for removing a customer and everything written for them."""

    async def test_an_unquoted_customer_can_be_deleted(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """A customer nobody has quoted is removable."""
        await service.delete("customer-1")

        customers.delete.assert_awaited_once_with("customer-1")

    async def test_a_quoted_customer_takes_their_quotes_with_them(
        self, service: CustomerService, quotes: AsyncMock, customers: AsyncMock
    ) -> None:
        """Every quote written for somebody is removed along with them.

        Notes:
            **This used to be a refusal**, and the change is deliberate.
            Stopping a customer is still the right answer for one who was
            really served and has really left — it keeps what was billed and
            who agreed to it — but the refusal left no way at all to remove a
            household entered by mistake, or the fixtures a test campaign is
            obliged to clean up after itself. A quote names one customer and
            means nothing without them, so it cannot outlive them.
        """
        quotes.list.return_value = [_quote()]

        await service.delete("customer-1")

        quotes.delete.assert_awaited_once_with("quote-1")
        customers.delete.assert_awaited_once_with("customer-1")

    async def test_the_quotes_go_before_the_customer(
        self, service: CustomerService, quotes: AsyncMock, customers: AsyncMock
    ) -> None:
        """Ordering matters: a quote outliving its customer is unprintable.

        Notes:
            Both writes share one transaction, so a failure at either step
            rolls the whole thing back. What this asserts is that the
            in-transaction ordering never leaves a quote pointing at a customer
            row the database has already dropped, which the foreign key would
            refuse anyway — as a 500 rather than as anything a caller can read.
        """
        order: List[str] = []
        quotes.list.return_value = [_quote()]
        # ``append`` answers None, and the service reads a falsy delete as
        # "nothing matched"; the ``or True`` is what keeps the double honest.
        quotes.delete.side_effect = lambda quote_id: order.append("quote") or True
        customers.delete.side_effect = (
            lambda customer_id: order.append("customer") or True
        )

        await service.delete("customer-1")

        assert order == ["quote", "customer"]

    async def test_a_quote_with_no_identifier_stops_the_deletion(
        self, service: CustomerService, quotes: AsyncMock, customers: AsyncMock
    ) -> None:
        """An unidentifiable quote is refused rather than skipped.

        Notes:
            Skipping it would delete the customer and leave the quote behind,
            which is the orphan this whole cascade exists to avoid.
        """
        quotes.list.return_value = [_quote().model_copy(update={"id": None})]

        with pytest.raises(MTCustomerHasQuotes):
            await service.delete("customer-1")

        customers.delete.assert_not_awaited()

    async def test_deleting_an_absent_customer_is_reported(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """A delete that matches nothing raises rather than passing silently."""
        customers.get.return_value = None

        with pytest.raises(MTCustomerNotFound):
            await service.delete("ghost")

    async def test_quotes_for_an_absent_customer_is_not_an_empty_list(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """ "No quotes" and "no such customer" are different answers.

        Notes:
            An empty list for an unknown identifier would let a typo read as a
            customer who happens to have been quoted nothing.
        """
        customers.get.return_value = None

        with pytest.raises(MTCustomerNotFound):
            await service.quotes_for("ghost")
