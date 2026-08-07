from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third-party imports
from sqlalchemy import Select, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import RegistrationStatus
from models.people.customer import Customer
from storage.mappers.people.customer_mapper import CustomerMapper
from storage.orm.people.customer_row import CustomerRow
from storage.orm.planning.intervention_row import InterventionRow
from storage.orm.quoting.quote_row import QuoteRow
from storage.repositories.base import BaseRepository


class CustomerRepository(BaseRepository[CustomerRow]):
    """Reads and writes customers.

    Attributes:
        mapper (CustomerMapper): Converts between rows and domain models.

    Notes:
        Every method takes and returns :class:`~models.people.customer.Customer`
        instances. The ORM row type never leaves this class.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        resolved_logger = logger if logger else getLogger(__name__)
        super().__init__(session=session, row_class=CustomerRow, logger=resolved_logger)
        self.mapper = CustomerMapper(logger=resolved_logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_query(
        self,
        search: Optional[str] = None,
        status: Optional[RegistrationStatus] = None,
    ) -> Select[Tuple[CustomerRow]]:
        """Build the filtered select shared by ``list`` and ``count``.

        Args:
            search (Optional[str]): Case-insensitive fragment.
            status (Optional[RegistrationStatus]): Restrict to one status.

        Returns:
            Select[Tuple[CustomerRow]]: The filtered statement, without ordering or pagination.

        Notes:
            Shared so a page and its total can never be computed from
            different filters.
        """
        statement = select(CustomerRow)
        if status is not None:
            statement = statement.where(CustomerRow.registration_status == status.value)
        if search:
            pattern = f"%{search.strip().lower()}%"
            statement = statement.where(
                or_(
                    CustomerRow.first_name.ilike(pattern),
                    CustomerRow.last_name.ilike(pattern),
                    CustomerRow.email.ilike(pattern),
                    CustomerRow.city.ilike(pattern),
                )
            )
        return statement

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, customer: Customer) -> Customer:
        """Insert a new customer.

        Args:
            customer (Customer): The customer to store.

        Returns:
            Customer: The stored customer, carrying its generated identifier
            and timestamps.

        Raises:
            SQLAlchemyError: If the insert fails.
        """
        self.logger.info("Creating customer %s.", customer.full_name())
        row = self.mapper.to_row(customer)
        self.session.add(row)
        await self.session.flush()
        self.logger.debug("Created customer row %s.", row.id)
        return self.mapper.to_model(row)

    async def get(self, customer_id: str) -> Optional[Customer]:
        """Return a customer by identifier.

        Args:
            customer_id (str): The identifier to look up.

        Returns:
            Optional[Customer]: The customer, or ``None`` when absent.
        """
        row = await self._get_row(customer_id)
        if row is None:
            self.logger.warning("Customer %s not found.", customer_id)
            return None
        return self.mapper.to_model(row)

    async def update(self, customer: Customer) -> Optional[Customer]:
        """Update an existing customer.

        Args:
            customer (Customer): The customer to store, carrying its
                identifier.

        Returns:
            Optional[Customer]: The updated customer, or ``None`` when no row
            matched the identifier.

        Raises:
            SQLAlchemyError: If the update fails.
        """
        if customer.id is None:
            self.logger.warning("Update requested for a customer with no id.")
            return None
        row = await self._get_row(customer.id)
        if row is None:
            self.logger.warning("Update requested for absent customer %s.", customer.id)
            return None
        self.mapper.apply_to_row(row, customer)
        await self.session.flush()
        self.logger.info("Updated customer %s.", customer.id)
        return self.mapper.to_model(row)

    async def set_status(
        self, customer_id: str, status: RegistrationStatus
    ) -> Optional[Customer]:
        """Change a customer's registration status.

        Args:
            customer_id (str): The customer to change.
            status (RegistrationStatus): The new status.

        Returns:
            Optional[Customer]: The updated customer, or ``None`` when absent.

        Notes:
            A dedicated method rather than a general update: stopping a
            customer is the one mutation a manager performs without touching
            any other field, and routing it through a full update would risk
            clobbering the rest of the record with a stale payload.
        """
        row = await self._get_row(customer_id)
        if row is None:
            self.logger.warning(
                "Status change requested for absent customer %s.", customer_id
            )
            return None
        self.logger.info("Setting customer %s status to %s.", customer_id, status.value)
        row.registration_status = status.value
        await self.session.flush()
        return self.mapper.to_model(row)

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
            search (Optional[str]): Case-insensitive fragment matched against
                the names, the email and the city.
            status (Optional[RegistrationStatus]): Restrict to one status.

        Returns:
            List[Customer]: The matching customers, ordered by family name.
        """
        self.logger.debug(
            "Listing customers: page=%d search=%r status=%s.",
            page,
            search,
            status.value if status else None,
        )
        statement = self._build_query(search=search, status=status)
        statement = statement.order_by(CustomerRow.last_name, CustomerRow.first_name)
        rows = await self._fetch_all(self._paginate(statement, page, size))
        if not rows:
            self.logger.warning("No customer matched the query.")
        return self.mapper.to_models(rows)

    async def count(
        self,
        search: Optional[str] = None,
        status: Optional[RegistrationStatus] = None,
    ) -> int:
        """Return how many customers match a query.

        Args:
            search (Optional[str]): Case-insensitive fragment matched against
                the names, the email and the city.
            status (Optional[RegistrationStatus]): Restrict to one status.

        Returns:
            int: The number of matching customers.
        """
        return await self._count(self._build_query(search=search, status=status))

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
            List[Customer]: The matching customers, by family name.

        Notes:
            - The portfolio is the **union** of two sets: customers the
              assistant has a planned intervention with, and customers of quotes
              they wrote. The union is what makes the screen usable — a newly
              hired assistant has no interventions yet, and with only the first
              half their customer list would be empty, so they could quote for
              nobody and the feature would appear broken on their first day.
            - **The two halves are keyed differently, and that is why both
              identifiers are taken.** An intervention names the assistant, so
              it joins on ``hca_id``; a quote records the *account* that wrote
              it — see :attr:`QuoteRow.authored_by` — so it joins on
              ``account_id``. Comparing ``authored_by`` to an assistant
              identifier matches nothing, which quietly reduced the union to its
              first half and produced exactly the empty first day described
              above.
            - Scoped in the statement rather than by filtering rows afterwards.
              A page of fifty narrowed to three has already read forty-seven
              customers this assistant is not entitled to.
        """
        by_intervention = select(InterventionRow.customer_id).where(
            InterventionRow.hca_id == hca_id
        )
        by_quote = select(QuoteRow.customer_id).where(
            QuoteRow.authored_by == account_id
        )
        statement = (
            self._build_query(search=search)
            .where(
                CustomerRow.id.in_(by_intervention.union(by_quote)),
            )
            .order_by(CustomerRow.last_name, CustomerRow.first_name)
        )
        self.logger.debug(
            "Listing the customer portfolio of assistant %s: page=%d search=%s.",
            hca_id,
            page,
            search,
        )
        rows = await self._fetch_all(self._paginate(statement, page, size))
        if not rows:
            self.logger.info(
                "Assistant %s has no customer yet: no planned visit and no "
                "quote of their own.",
                hca_id,
            )
        return self.mapper.to_models(rows)

    async def is_served_by(
        self, customer_id: str, hca_id: str, account_id: str
    ) -> bool:
        """Return whether a customer is in an assistant's portfolio.

        Args:
            customer_id (str): The customer being opened.
            hca_id (str): The assistant asking.
            account_id (str): The sign-in account that assistant holds.

        Returns:
            bool: ``True`` when the assistant may see that customer.

        Notes:
            - Asked before serving a single customer, so guessing an identifier
              does not reach somebody else's file. A care agency's customer
              record carries an address, a telephone number and a care schedule;
              it is not something to hand to whoever asks.
            - The same two-keyed union as :meth:`list_for_hca`, and it has to
              stay that way: a portfolio that lists a customer the detail view
              then refuses is worse than either behaviour on its own.
        """
        by_intervention = select(InterventionRow.customer_id).where(
            InterventionRow.hca_id == hca_id,
            InterventionRow.customer_id == customer_id,
        )
        by_quote = select(QuoteRow.customer_id).where(
            QuoteRow.authored_by == account_id,
            QuoteRow.customer_id == customer_id,
        )
        statement = select(CustomerRow.id).where(
            CustomerRow.id == customer_id,
            CustomerRow.id.in_(by_intervention.union(by_quote)),
        )
        found = await self._fetch_one(statement)
        if found is None:
            self.logger.warning(
                "Assistant %s asked for customer %s, who is not theirs.",
                hca_id,
                customer_id,
            )
        return found is not None

    async def delete(self, customer_id: str) -> bool:
        """Delete a customer.

        Args:
            customer_id (str): The customer to delete.

        Returns:
            bool: ``True`` when a row was deleted.

        Raises:
            SQLAlchemyError: If a quote still references the customer.
        """
        try:
            return await self._delete_row(customer_id)
        except SQLAlchemyError as exc:
            self.logger.error("Error deleting customer %s: %s.", customer_id, exc)
            raise
