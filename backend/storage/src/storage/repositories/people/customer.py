from __future__ import annotations

# Standard library imports
from datetime import date
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third-party imports
from sqlalchemy import (
    ColumnElement,
    CompoundSelect,
    Select,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

# First-party imports
from models.enums import BillingPeriodicity, QuoteStatus, RegistrationStatus
from models.people.customer import Customer
from models.schemas.requests.customers.customer_filter import CustomerFilter
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

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        super().__init__(session=session, row_class=CustomerRow)
        self.mapper = CustomerMapper()

    ############################
    # Internal Helpers Methods #
    ############################

    def _ongoing_arrangement(self) -> Select[Tuple[int]]:
        """Return the correlated subquery for "is being served right now".

        Returns:
            Select[Tuple[int]]: A statement to use with ``.exists()``.

        Notes:
            - **The definition of an ongoing arrangement, in one place.** Accepted,
              and not past its interruption date — which is inclusive, so a quote
              interrupted today is still running today.
            - Deliberately narrower than the customer drawer's notion of "in
              flight", which also counts quotes that are merely sent or awaiting
              validation. Those answer *what is in the pipeline*. This answers
              *who are we serving*, which is the question a manager filters the
              book by. The two are allowed to differ, and this note is so they
              differ on purpose rather than by drift.
        """
        today = date.today()
        self.logger.debug("Building the ongoing-arrangement subquery for %s.", today)  # noqa: E501
        self.logger.info("Ongoing means accepted and not interrupted before %s.", today)
        if today.year < 2000:
            self.logger.error(
                "The host clock says %s, so every arrangement looks ongoing. "
                "The ongoing filter cannot be trusted until it is corrected.",
                today,
            )
        elif today.month == 12 and today.day == 31:
            self.logger.warning(
                "Reading ongoing arrangements on %s: the comparison is "
                "inclusive, so an arrangement interrupted today is still "
                "ongoing today and drops out tomorrow.",
                today,
            )
        return (
            select(literal(1))
            .select_from(QuoteRow)
            .where(
                QuoteRow.customer_id == CustomerRow.id,
                QuoteRow.status == QuoteStatus.ACCEPTED.value,
                or_(
                    QuoteRow.interrupted_on.is_(None),
                    QuoteRow.interrupted_on >= today,
                ),
            )
        )

    def _dialable_digits(
        self, column: InstrumentedAttribute[str]
    ) -> ColumnElement[str]:
        """Return a telephone column reduced to its bare digits, in SQL.

        Args:
            column (InstrumentedAttribute[str]): The telephone column.

        Returns:
            ColumnElement[str]: The column with its punctuation removed.

        Notes:
            - **A stored number does not look like a typed one.** Pydantic's
              ``PhoneNumber`` normalises on the way in, so ``+33699999999`` is
              stored as ``tel:+33-6-99-99-99-99``. A manager typing any of the
              forms they know — ``0699999999``, ``+33 6 99…``, or the last six
              digits off a caller display — would match none of it.
            - So both sides are reduced to digits before comparing. ``replace``
              is the one string function SQLite and PostgreSQL spell the same
              way, which is why this is three nested calls rather than a regular
              expression.
        """
        self.logger.debug("Reducing %s to its dialable digits.", column.key)
        self.logger.info("Telephone matching compares digits, not stored text.")
        if column.key != "phone_number":
            self.logger.error(
                "Column %s is not a telephone number. Digit-stripping it will "
                "match something other than what was asked for.",
                column.key,
            )
        elif column.type.length is not None and column.type.length < 16:
            self.logger.warning(
                "Column %s holds at most %d characters, which is shorter than a "
                "normalised international number; stored values may be cut off.",
                column.key,
                column.type.length,
            )
        stripped = func.replace(column, "tel:", "")
        stripped = func.replace(stripped, "-", "")
        stripped = func.replace(stripped, " ", "")
        return func.replace(stripped, "+", "")

    def _build_query(
        self,
        search: Optional[str] = None,
        status: Optional[RegistrationStatus] = None,
        customer_filter: Optional[CustomerFilter] = None,
        customer_ids: Optional[List[str]] = None,
    ) -> Select[Tuple[CustomerRow]]:
        """Build the filtered select shared by ``list`` and ``count``.

        Args:
            search (Optional[str]): Case-insensitive fragment.
            status (Optional[RegistrationStatus]): Restrict to one status.
            customer_filter (Optional[CustomerFilter]): The richer filter. Its
                ``search`` and ``status`` win over the two positional arguments
                when both are given.
            customer_ids (Optional[List[str]]): The households the caller may
                read. ``None`` means every household. An **empty list means
                none**.

        Returns:
            Select[Tuple[CustomerRow]]: The filtered statement, without ordering or pagination.

        Notes:
            - Shared so a page and its total can never be computed from
              different filters.
            - ``search`` and ``status`` survive as parameters because
              :meth:`list_for_hca` and the assistant's portfolio still pass them
              on their own. A caller with a :class:`CustomerFilter` passes that
              instead and the two named arguments fall away.
        """
        applied = customer_filter or CustomerFilter()
        self.logger.debug(
            "Building the customer query from %s.",
            applied.model_dump(exclude_none=True),
        )
        if customer_filter is not None and search and applied.search:
            self.logger.warning(
                "Two searches were passed (%r and %r). The filter's %r is used.",
                search,
                applied.search,
                applied.search,
            )
        search = applied.search or search
        status = applied.status or status
        if applied.is_empty() and search is None and status is None:
            self.logger.info("No filter was given. The query is the whole book.")

        statement = select(CustomerRow)
        if customer_ids is not None:
            # A permission rather than a filter, applied in the statement for
            # the reason `authored_by` is on the quote side. `None` and `[]` are
            # opposites: reading the empty list as falsy would show a manager
            # who runs no team the whole customer book.
            if not customer_ids:
                self.logger.warning(
                    "The caller may read no household. The query matches nothing."
                )
            statement = statement.where(CustomerRow.id.in_(customer_ids))
        if status is not None:
            statement = statement.where(CustomerRow.registration_status == status.value)  # noqa: E501
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
        # One column each, unlike ``search``: a manager who has decided the
        # fragment is a postcode does not want it matched against a surname.
        for fragment, column in (
            (applied.city, CustomerRow.city),
            (applied.postal_code, CustomerRow.postal_code),
            (applied.email, CustomerRow.email),
        ):
            if fragment:
                statement = statement.where(
                    column.ilike(f"%{fragment.strip().lower()}%")
                )
        if applied.phone:
            typed = "".join(
                character for character in applied.phone if character.isdigit()
            )
            if not typed:
                # Everything the manager typed was punctuation, so the predicate
                # would be `LIKE '%%'` — every customer, under a filter that
                # says it is narrowing by telephone number.
                self.logger.error(
                    "Telephone filter %r holds no digit. It is dropped rather "
                    "than matched as a wildcard.",
                    applied.phone,
                )
            if typed:
                statement = statement.where(
                    self._dialable_digits(CustomerRow.phone_number).like(f"%{typed}%")
                )
        if applied.is_geocoded is not None:
            resolved = CustomerRow.latitude.is_not(None) & CustomerRow.longitude.is_not(  # noqa: E501
                None
            )
            statement = statement.where(resolved if applied.is_geocoded else ~resolved)
        if applied.has_ongoing_arrangement is not None:
            ongoing = self._ongoing_arrangement().exists()
            statement = statement.where(
                ongoing if applied.has_ongoing_arrangement else ~ongoing
            )
        return statement

    def _portfolio_scope(self, hca_id: str, account_id: str) -> CompoundSelect:
        """Return the statement selecting the customers an assistant may see.

        Args:
            hca_id (str): The assistant whose portfolio is being scoped.
            account_id (str): The sign-in account that assistant holds.

        Returns:
            CompoundSelect: A statement yielding customer identifiers.

        Notes:
            - **One definition of the portfolio, three readers.** The list, the
              single-customer check and the planning rail all have to agree. A
              rail that offers a household whose detail view then refuses is
              worse than either behaviour alone. Written once here, the three
              cannot drift.
            - The portfolio is the **union** of two sets: customers the
              assistant has a planned intervention with, and customers of quotes
              they wrote. Without the second half a newly hired assistant's list
              is empty on their first day, so they can quote for nobody and the
              feature looks broken.
            - **The two halves are keyed differently, and that is why both
              identifiers are taken.** An intervention names the assistant, so
              it joins on ``hca_id``. A quote records the *account* that wrote
              it — see :attr:`QuoteRow.authored_by` — so it joins on
              ``account_id``. Comparing ``authored_by`` to an assistant
              identifier matches nothing, which quietly reduces the union to its
              first half.
        """
        by_intervention = select(InterventionRow.customer_id).where(
            InterventionRow.hca_id == hca_id
        )
        by_quote = select(QuoteRow.customer_id).where(
            QuoteRow.authored_by == account_id
        )
        return by_intervention.union(by_quote)

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
            self.logger.warning("Update requested for absent customer %s.", customer.id)  # noqa: E501
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
        self.logger.info("Setting customer %s status to %s.", customer_id, status.value)  # noqa: E501
        row.registration_status = status.value
        await self.session.flush()
        return self.mapper.to_model(row)

    async def set_billing_periodicity(
        self, customer_id: str, periodicity: Optional[BillingPeriodicity]
    ) -> Optional[Customer]:
        """Give a customer their own invoicing granularity, or take it away.

        Args:
            customer_id (str): The customer to change.
            periodicity (Optional[BillingPeriodicity]): The rule to bill them
                on, or ``None`` to put them back on the agency's own.

        Returns:
            Optional[Customer]: The updated customer, or ``None`` when absent.

        Notes:
            A dedicated writer for the reason :meth:`set_status` is one: this
            is a change a manager makes on its own, from a screen holding a
            customer record that may be minutes old, and routing it through a
            full update would let that stale copy overwrite an address somebody
            else corrected in the meantime.
        """
        row = await self._get_row(customer_id)
        if row is None:
            self.logger.warning(
                "A billing periodicity was set for the absent customer %s.",
                customer_id,
            )
            return None
        self.logger.info(
            "Customer %s is now billed %s.",
            customer_id,
            periodicity.value if periodicity else "on the agency's own rule",
        )
        row.billing_periodicity = periodicity.value if periodicity else None
        await self.session.flush()
        return self.mapper.to_model(row)

    async def list_billing_periodicities(self) -> List[BillingPeriodicity]:
        """Return the granularities customers have asked for by name.

        Returns:
            List[BillingPeriodicity]: Every distinct override in the book, in a
            stable order. Empty when every customer follows the agency.

        Notes:
            **This is what stops a billing run reading a whole year of quotes
            every month.** A run has to look far enough back and forward to
            catch every customer's own window, and the widest of those windows
            is decided by the periodicities actually in use — which is a single
            ``DISTINCT`` rather than an assumption. With no override anywhere,
            the answer is empty and the run spans exactly the agency's own
            window, as it did before customers could differ.
        """
        statement = select(CustomerRow.billing_periodicity).where(
            CustomerRow.billing_periodicity.is_not(None)
        )
        result = await self.session.execute(statement.distinct())
        found = [
            BillingPeriodicity(value)
            for value in sorted(result.scalars().all())
            if value in BillingPeriodicity.values()
        ]
        self.logger.debug(
            "%d customer periodicit(ies) differ from the agency's: %s.",
            len(found),
            ", ".join(periodicity.value for periodicity in found) or "none",
        )
        return found

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        search: Optional[str] = None,
        status: Optional[RegistrationStatus] = None,
        customer_filter: Optional[CustomerFilter] = None,
        customer_ids: Optional[List[str]] = None,
    ) -> List[Customer]:
        """Return a page of customers.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            search (Optional[str]): Case-insensitive fragment matched against
                the names, the email and the city.
            status (Optional[RegistrationStatus]): Restrict to one status.
            customer_filter (Optional[CustomerFilter]): The richer filter.
            customer_ids (Optional[List[str]]): The households the caller may
                read. ``None`` means every household. An empty list means none.

        Returns:
            List[Customer]: The matching customers, ordered by family name.
        """
        self.logger.debug(
            "Listing customers: page=%d search=%r status=%s filter=%s.",
            page,
            search,
            status.value if status else None,
            customer_filter.model_dump(exclude_none=True) if customer_filter else None,  # noqa: E501
        )
        statement = self._build_query(
            search=search,
            status=status,
            customer_filter=customer_filter,
            customer_ids=customer_ids,
        )
        statement = statement.order_by(CustomerRow.last_name, CustomerRow.first_name)  # noqa: E501
        try:
            rows = await self._fetch_all(self._paginate(statement, page, size))
        except SQLAlchemyError:
            self.logger.error(
                "The customer query failed on page %d for filter=%s.",
                page,
                customer_filter.model_dump(exclude_none=True)
                if customer_filter
                else None,
            )
            raise
        if not rows:
            self.logger.warning("No customer matched the query.")
        self.logger.info("Read %d customers on page %d.", len(rows), page)
        return self.mapper.to_models(rows)

    async def count(
        self,
        search: Optional[str] = None,
        status: Optional[RegistrationStatus] = None,
        customer_filter: Optional[CustomerFilter] = None,
        customer_ids: Optional[List[str]] = None,
    ) -> int:
        """Return how many customers match a query.

        Args:
            search (Optional[str]): Case-insensitive fragment matched against
                the names, the email and the city.
            status (Optional[RegistrationStatus]): Restrict to one status.
            customer_filter (Optional[CustomerFilter]): The richer filter.
            customer_ids (Optional[List[str]]): The households the caller may
                read, so the total is narrowed exactly as the page is.

        Returns:
            int: The number of matching customers.
        """
        self.logger.debug(
            "Counting customers: search=%r status=%s filter=%s.",
            search,
            status.value if status else None,
            customer_filter.model_dump(exclude_none=True) if customer_filter else None,  # noqa: E501
        )
        try:
            total = await self._count(
                self._build_query(
                    search=search,
                    status=status,
                    customer_filter=customer_filter,
                    customer_ids=customer_ids,
                )
            )
        except SQLAlchemyError:
            self.logger.error("Counting customers failed for search=%r.", search)  # noqa: E501
            raise
        if total == 0:
            self.logger.warning("No customer matched the counted query.")
        self.logger.info("%d customers match.", total)
        return total

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
              it joins on ``hca_id``. A quote records the *account* that wrote
              it — see :attr:`QuoteRow.authored_by` — so it joins on
              ``account_id``. Comparing ``authored_by`` to an assistant
              identifier matches nothing, which quietly reduced the union to its
              first half and produced exactly the empty first day described
              above.
            - Scoped in the statement rather than by filtering rows afterwards.
              A page of fifty narrowed to three has already read forty-seven
              customers this assistant is not entitled to.
        """
        statement = (
            self._build_query(search=search)
            .where(CustomerRow.id.in_(self._portfolio_scope(hca_id, account_id)))
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

    async def portfolio_ids(self, hca_id: str, account_id: str) -> List[str]:
        """Return every customer an assistant is entitled to see.

        Args:
            hca_id (str): The assistant whose portfolio is being read.
            account_id (str): The sign-in account that assistant holds.

        Returns:
            List[str]: Their customers' identifiers, in a stable order.

        Notes:
            - **Not ``list_for_hca(size=None)``**, and the difference is a bug
              waiting to happen: :meth:`~storage.repositories.base.BaseRepository._paginate`
              turns an absent size into the default page of a hundred. A screen
              built from that would silently omit the hundred-and-first
              household — a calendar missing a family, with nothing on it
              saying so.
            - Identifiers only. The caller that needs the records asks for them
              by name afterwards. A rail of forty households does not need forty
              addresses and telephone numbers read out of the database to draw
              it.
            - Ordered so two reads of an unchanged portfolio produce the same
              rail rather than the same set in a different order.
        """
        statement = (
            select(CustomerRow.id)
            .where(CustomerRow.id.in_(self._portfolio_scope(hca_id, account_id)))  # noqa: E501
            .order_by(CustomerRow.last_name, CustomerRow.first_name)
        )
        rows = await self.session.execute(statement)
        identifiers = [row[0] for row in rows.all()]
        if not identifiers:
            self.logger.info(
                "Assistant %s has no customer yet: no planned visit and no "
                "quote of their own.",
                hca_id,
            )
        self.logger.debug(
            "Assistant %s has %d customer(s) in their portfolio.",
            hca_id,
            len(identifiers),
        )
        return identifiers

    async def list_by_ids(self, customer_ids: List[str]) -> List[Customer]:
        """Return several customers at once.

        Args:
            customer_ids (List[str]): The customers wanted.

        Returns:
            List[Customer]: The matching customers, by family name. Identifiers
            that match nothing are simply absent.

        Notes:
            - Exists to replace a loop of :meth:`get` calls. Drawing a rail of
              four hundred households one query at a time is four hundred round
              trips on a screen somebody opens every morning.
            - **An empty input answers without a query.** ``IN ()`` is a syntax
              error on some engines and a pointless round trip on the rest, and
              an empty portfolio is an ordinary state rather than an error.
            - The caller decides what a missing identifier means. Here it can
              only be a household deleted between two reads, which is a rail
              entry that quietly disappears rather than a failure.
        """
        if not customer_ids:
            self.logger.debug("No customer identifier was given; reading none.")
            return []
        statement = (
            self._build_query()
            .where(CustomerRow.id.in_(customer_ids))
            .order_by(CustomerRow.last_name, CustomerRow.first_name)
        )
        rows = await self._fetch_all(statement)
        if len(rows) != len(set(customer_ids)):
            self.logger.warning(
                "Asked for %d customer(s) and found %d; some no longer exist.",
                len(set(customer_ids)),
                len(rows),
            )
        self.logger.debug("Read %d customer(s) by identifier.", len(rows))
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
        statement = select(CustomerRow.id).where(
            CustomerRow.id == customer_id,
            CustomerRow.id.in_(self._portfolio_scope(hca_id, account_id)),
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
            self.logger.error("Error deleting customer %s: %s.", customer_id, exc)  # noqa: E501
            raise
