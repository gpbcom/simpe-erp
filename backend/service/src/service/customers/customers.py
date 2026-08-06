from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# First-party imports
from models.enums import RegistrationStatus
from models.people.customer import Customer
from models.quoting.quote import Quote
from service.customers.exceptions import (  # noqa: E501
    MTCustomerHasQuotes,
    MTCustomerNotFound,
)
from storage.repositories.customer import CustomerRepository
from storage.repositories.quote import QuoteRepository


class CustomerService:
    """Manages the people the agency works for.

    Attributes:
        customers (CustomerRepository): The customer store.
        quotes (QuoteRepository): The quote store, consulted before a delete.
        logger (Logger): Logger for customer operations.

    Notes:
        A customer is stopped rather than deleted once they have been quoted.
        The quote is an accounting record naming them, and removing the row it
        points at would leave a figure on a ledger with nobody attached to it.
    """

    def __init__(
        self,
        customers: CustomerRepository,
        quotes: QuoteRepository,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            customers (CustomerRepository): The customer store.
            quotes (QuoteRepository): The quote store.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.customers = customers
        self.quotes = quotes
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("CustomerService created.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, customer: Customer) -> Customer:
        """Register a customer.

        Args:
            customer (Customer): The customer to register.

        Returns:
            Customer: The stored customer.

        Notes:
            The address geocodes itself during validation, so a customer
            arriving here already carries a coordinate or an explanation of why
            it has none. Nothing is refused on that basis — a customer whose
            street the map does not know is still a customer — but the warning
            below is what explains, later, why their work went unplanned.
        """
        self.logger.info(
            "Registering customer %s %s.", customer.first_name, customer.last_name
        )
        if not customer.address.is_geocoded():
            self.logger.warning(
                "Customer %s %s has no coordinate (%s); their work cannot be "
                "planned until the address resolves.",
                customer.first_name,
                customer.last_name,
                customer.address.geocoding_error,
            )
        stored = await self.customers.create(customer)
        self.logger.debug("Customer stored as %s.", stored.id)
        return stored

    async def get(self, customer_id: str) -> Customer:
        """Return one customer.

        Args:
            customer_id (str): The customer to read.

        Returns:
            Customer: The customer.

        Raises:
            MTCustomerNotFound: If no such customer exists.
        """
        self.logger.debug("Reading customer %s.", customer_id)
        customer = await self.customers.get(customer_id)
        if customer is None:
            self.logger.warning("Customer %s does not exist.", customer_id)
            raise MTCustomerNotFound(f"No customer {customer_id!r} exists.")
        return customer

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        search: Optional[str] = None,
        status: Optional[RegistrationStatus] = None,
    ) -> List[Customer]:
        """Return a page of customers.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            search (Optional[str]): Case-insensitive fragment of a name.
            status (Optional[RegistrationStatus]): Restrict to one status.

        Returns:
            List[Customer]: The matching customers.
        """
        self.logger.debug(
            "Listing customers: page=%d search=%r status=%s.",
            page,
            search,
            status.value if status else None,
        )
        customers = await self.customers.list(
            page=page, size=size, search=search, status=status
        )
        if not customers:
            self.logger.warning(
                "No customer matches search=%r status=%s.",
                search,
                status.value if status else None,
            )
        return customers

    async def list_for_hca(
        self,
        hca_id: str,
        account_id: str,
        page: int = 1,
        size: Optional[int] = None,
        search: Optional[str] = None,
    ) -> List[Customer]:
        """Return the customers one assistant is entitled to see.

        Args:
            hca_id (str): The assistant whose portfolio is being read.
            account_id (str): The sign-in account that assistant holds.
            page (int): One-based page number.
            size (Optional[int]): Page size.
            search (Optional[str]): Restrict by name or address.

        Returns:
            List[Customer]: The assistant's own portfolio.

        Notes:
            Both identifiers, because the portfolio is a union of a set keyed
            by the assistant and a set keyed by their account. See
            :meth:`CustomerRepository.list_for_hca`.
        """
        return await self.customers.list_for_hca(
            hca_id=hca_id,
            account_id=account_id,
            page=page,
            size=size,
            search=search,
        )

    async def get_for_hca(
        self, customer_id: str, hca_id: str, account_id: str
    ) -> Customer:
        """Return one customer, if the assistant is entitled to see them.

        Args:
            customer_id (str): The customer to read.
            hca_id (str): The assistant asking.
            account_id (str): The sign-in account that assistant holds.

        Returns:
            Customer: The customer.

        Raises:
            MTCustomerNotFound: If the customer does not exist, or is not in
                the assistant's portfolio.

        Notes:
            The entitlement check comes **first**, and its failure is reported
            as "not found" rather than "not yours". A distinct answer would let
            an assistant walk the identifier space and learn which customers the
            agency has, which is most of what a customer list is worth.
        """
        if not await self.customers.is_served_by(customer_id, hca_id, account_id):
            raise MTCustomerNotFound(f"No customer {customer_id!r} exists.")
        return await self.get(customer_id)

    async def update(self, customer_id: str, customer: Customer) -> Customer:
        """Replace a customer's details.

        Args:
            customer_id (str): The customer to change.
            customer (Customer): The new details.

        Returns:
            Customer: The updated customer.

        Raises:
            MTCustomerNotFound: If no such customer exists.

        Notes:
            The identifier comes from the path, not the payload. Trusting the
            body would let a well-formed request rewrite a different customer
            than the one the caller addressed.
        """
        self.logger.info("Updating customer %s.", customer_id)
        updated = await self.customers.update(
            customer.model_copy(update={"id": customer_id})
        )
        if updated is None:
            self.logger.warning("Cannot update the absent customer %s.", customer_id)
            raise MTCustomerNotFound(f"No customer {customer_id!r} exists.")
        return updated

    async def set_status(
        self, customer_id: str, status: RegistrationStatus
    ) -> Customer:
        """Activate or stop a customer.

        Args:
            customer_id (str): The customer to change.
            status (RegistrationStatus): The new registration status.

        Returns:
            Customer: The updated customer.

        Raises:
            MTCustomerNotFound: If no such customer exists.

        Notes:
            Stopping a customer does not touch their quotes. Work already
            accepted stays schedulable, which is deliberate — a customer
            stopping at the end of the month still has this month's visits.
        """
        self.logger.info("Setting customer %s to %s.", customer_id, status.value)
        updated = await self.customers.set_status(customer_id, status)
        if updated is None:
            self.logger.warning(
                "Cannot change the status of the absent customer %s.", customer_id
            )
            raise MTCustomerNotFound(f"No customer {customer_id!r} exists.")
        if status is RegistrationStatus.STOPPED:
            self.logger.warning(
                "Customer %s is stopped; their accepted work still stands.",
                customer_id,
            )
        return updated

    async def quotes_for(self, customer_id: str) -> List[Quote]:
        """Return every quote issued to a customer.

        Args:
            customer_id (str): The customer to read.

        Returns:
            List[Quote]: Their quotes, newest first.

        Raises:
            MTCustomerNotFound: If no such customer exists.

        Notes:
            The customer is resolved first so an unknown identifier answers 404
            rather than an empty list — "this customer has no quotes" and "this
            customer does not exist" are different answers.
        """
        await self.get(customer_id)
        quotes = await self.quotes.list(customer_id=customer_id)
        self.logger.info("Customer %s has %d quote(s).", customer_id, len(quotes))
        return quotes

    async def delete(self, customer_id: str) -> None:
        """Remove a customer who has never been quoted.

        Args:
            customer_id (str): The customer to remove.

        Raises:
            MTCustomerNotFound: If no such customer exists.
            MTCustomerHasQuotes: If any quote names them.

        Notes:
            The check is here rather than left to the foreign key. The
            constraint would raise an ``IntegrityError`` that reaches the
            client as a 500; refusing explicitly answers 409 and says why.
        """
        await self.get(customer_id)
        quotes = await self.quotes.list(customer_id=customer_id)
        if quotes:
            self.logger.warning(
                "Refusing to delete customer %s: %d quote(s) name them.",
                customer_id,
                len(quotes),
            )
            raise MTCustomerHasQuotes(
                f"Customer {customer_id!r} has {len(quotes)} quote(s) and "
                f"cannot be deleted. Set their status to 'stopped' instead."
            )
        removed = await self.customers.delete(customer_id)
        if not removed:
            self.logger.error(
                "Customer %s vanished between the read and the delete.",
                customer_id,
            )
            raise MTCustomerNotFound(f"No customer {customer_id!r} exists.")
        self.logger.info("Customer %s deleted.", customer_id)
