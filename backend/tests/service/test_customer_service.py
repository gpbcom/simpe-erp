from __future__ import annotations

# Standard library imports
from typing import Optional
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.enums import QuoteStatus, RegistrationStatus
from models.people.customer import Customer
from models.quoting.quote import Quote
from service.customers.customers import CustomerService
from service.customers.exceptions import MTCustomerHasQuotes, MTCustomerNotFound


def _customer(
    customer_id: str = "customer-1",
    latitude: Optional[float] = 48.8566,
    longitude: Optional[float] = 2.3522,
    status: RegistrationStatus = RegistrationStatus.ACTIVE,
) -> Customer:
    """Build a customer.

    Args:
        customer_id (str): The identifier to assign.
        latitude (Optional[float]): The resolved latitude, if any.
        longitude (Optional[float]): The resolved longitude, if any.
        status (RegistrationStatus): Their registration status.

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
    )


def _quote() -> Quote:
    """Build a quote naming the customer.

    Returns:
        Quote: The quote.
    """
    return Quote(
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
            page=2, size=10, search="dur", status=RegistrationStatus.ACTIVE
        )


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


class TestCustomerDeletion:
    """Tests for the rule protecting quoted customers."""

    async def test_an_unquoted_customer_can_be_deleted(
        self, service: CustomerService, customers: AsyncMock
    ) -> None:
        """A customer nobody has quoted is removable."""
        await service.delete("customer-1")

        customers.delete.assert_awaited_once_with("customer-1")

    async def test_a_quoted_customer_is_refused(
        self, service: CustomerService, quotes: AsyncMock, customers: AsyncMock
    ) -> None:
        """Deleting somebody named on a quote is refused, not attempted.

        Notes:
            **Checked here rather than left to the foreign key.** The database
            would raise an ``IntegrityError`` that reaches the client as an
            opaque 500; refusing explicitly answers 409 and says to stop the
            customer instead.
        """
        quotes.list.return_value = [_quote()]

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
