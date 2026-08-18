from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from sqlalchemy.exc import SQLAlchemyError

# First-party imports
from models.enums import BillingPeriodicity, RegistrationStatus
from models.people.customer import Customer
from models.quoting.quote import Quote
from models.schemas.requests.customers.customer_filter import CustomerFilter
from service.customers.exceptions import (  # noqa: E501
    MTCustomerHasQuotes,
    MTCustomerNotFound,
    MTCustomerNotPromotable,
)
from storage.repositories.auth.user import UserRepository
from storage.repositories.people.customer import CustomerRepository
from storage.repositories.quoting.quote import QuoteRepository


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
        users: Optional[UserRepository] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            customers (CustomerRepository): The customer store.
            quotes (QuoteRepository): The quote store.
            users (Optional[UserRepository]): The account store, needed only to
                take a household's portal account with them when they are
                deleted. Optional so the many call sites that never delete —
                and every existing test — keep working unchanged.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.customers = customers
        self.quotes = quotes
        self.users = users
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("CustomerService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _remove_portal_account(self, customer_id: str) -> None:
        """Remove the household's portal account, so the customer can go.

        Args:
            customer_id (str): The customer being deleted.

        Notes:
            - ``users.customer_id`` is a foreign key with ``ON DELETE
              RESTRICT``, so a household holding an account cannot be deleted
              until the account is. Without this the delete answers 500 from a
              constraint, which reads as the server being broken rather than as
              the household having a login.
            - Mirrors what removing an assistant already does, and for the same
              reason: an account whose link names nothing cannot pass the
              row-level check, so it could sign in and reach nothing.
            - Skipped entirely when no account store is wired in, which is
              every caller that never deletes.
        """
        if self.users is None:
            self.logger.debug(
                "No account store is wired in; customer %s is removed alone.",
                customer_id,
            )
            return
        account = await self.users.get_by_customer_id(customer_id)
        if account is None:
            self.logger.debug("Customer %s holds no portal account.", customer_id)
            return
        if account.id is None:
            self.logger.error(
                "The portal account of customer %s carries no identifier and "
                "cannot be deleted. The customer stays.",
                customer_id,
            )
            raise MTCustomerHasQuotes(
                f"Customer {customer_id!r} has a portal account that cannot be "
                f"identified, so it cannot be removed with them."
            )
        self.logger.warning(
            "Deleting the portal account %s of customer %s. They lose access "
            "to their space.",
            account.email,
            customer_id,
        )
        await self.users.delete(account.id)
        self.logger.info("Portal account of customer %s deleted.", customer_id)

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
                "Customer %s %s has no coordinate (%s). Their work cannot be "
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
        customer_filter: Optional[CustomerFilter] = None,
        customer_ids: Optional[List[str]] = None,
    ) -> List[Customer]:
        """Return a page of customers.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            search (Optional[str]): Case-insensitive fragment of a name.
            status (Optional[RegistrationStatus]): Restrict to one status.
            customer_filter (Optional[CustomerFilter]): The richer filter the
                customers screen sends.
            customer_ids (Optional[List[str]]): The households the caller may
                read. ``None`` means every household. An empty list means none.

        Returns:
            List[Customer]: The matching customers.

        Notes:
            ``customer_ids`` is the caller's *scope*, resolved by
            :meth:`~service.organisation.teams.TeamService.readable_customer_ids`
            and passed straight to the statement — never applied to the page
            afterwards, which would have read households the caller may not see.
        """
        self.logger.debug(
            "Listing customers: page=%d search=%r status=%s filter=%s.",
            page,
            search,
            status.value if status else None,
            customer_filter.model_dump(exclude_none=True) if customer_filter else None,
        )
        try:
            customers = await self.customers.list(
                page=page,
                size=size,
                search=search,
                status=status,
                customer_filter=customer_filter,
                customer_ids=customer_ids,
            )
        except SQLAlchemyError:
            # Named here rather than left to the handler: the filter is eight
            # fields wide now, and "the customer book failed to load" with no
            # record of what was asked for is unactionable.
            self.logger.error(
                "Reading the customer book failed for filter=%s.",
                customer_filter.model_dump(exclude_none=True)
                if customer_filter
                else None,
            )
            raise
        if not customers:
            self.logger.warning(
                "No customer matches search=%r status=%s.",
                search,
                status.value if status else None,
            )
        self.logger.info("Listed %d customers on page %d.", len(customers), page)
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
            self.logger.warning("Cannot update the absent customer %s.", customer_id)  # noqa: E501
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
            - Any transition is accepted here, deliberately: stopping an active
              customer and reinstating a stopped one are ordinary corrections.
              The one transition with a rule — promoting a prospect — has its
              own method, :meth:`promote`.
            - Changing the status does not touch their quotes. What it changes
              is whether the planner will *place* them: only an active customer
              is scheduled, so stopping somebody, or moving them back to
              prospect, takes their accepted work out of the next run while
              leaving the quotes themselves intact and readable.
        """
        self.logger.debug(
            "Changing customer %s to %s; schedulable=%s.",
            customer_id,
            status.value,
            status.can_be_scheduled(),
        )
        self.logger.info("Setting customer %s to %s.", customer_id, status.value)
        try:
            updated = await self.customers.set_status(customer_id, status)
        except SQLAlchemyError:
            self.logger.error(
                "Writing status %s for customer %s failed.", status.value, customer_id
            )
            raise
        if updated is None:
            self.logger.warning(
                "Cannot change the status of the absent customer %s.", customer_id
            )
            raise MTCustomerNotFound(f"No customer {customer_id!r} exists.")
        if not status.can_be_scheduled():
            self.logger.warning(
                "Customer %s is now %s. Their accepted work stands but no "
                "further visit will be planned for them.",
                customer_id,
                status.value,
            )
        return updated

    async def set_billing_periodicity(
        self,
        customer_id: str,
        periodicity: Optional[BillingPeriodicity],
        actor: str,
    ) -> Customer:
        """Give a customer their own invoicing granularity, or take it away.

        Args:
            customer_id (str): The customer to change.
            periodicity (Optional[BillingPeriodicity]): The rule to bill them
                on, or ``None`` to put them back on the agency's own.
            actor (str): The manager or administrator making the change.

        Returns:
            Customer: The updated customer.

        Raises:
            MTCustomerNotFound: If no such customer exists.

        Notes:
            - **It applies to the next run and re-issues nothing.** An invoice
              already written keeps the period it was written for, so moving a
              customer from monthly to weekly does not split last month's
              document in four — it decides what the next run bills them over.
            - Logged at warning, naming who did it: this changes how often a
              customer is asked for money, which is a commercial decision
              somebody made rather than a preference somebody toggled.
            - Any change is accepted, including one taken mid-period. The guard
              against that costing a customer a second invoice for days they
              have already paid for lives where it can see the invoices —
              :meth:`~service.billing.billings.BillingService.generate_for_customer`
              refuses a window overlapping one already billed.
        """
        self.logger.debug(
            "Changing the billing periodicity of customer %s.", customer_id
        )
        try:
            updated = await self.customers.set_billing_periodicity(
                customer_id, periodicity
            )
        except SQLAlchemyError:
            self.logger.error(
                "Writing the billing periodicity of customer %s failed.",
                customer_id,
            )
            raise
        if updated is None:
            self.logger.warning(
                "Cannot set the billing periodicity of the absent customer %s.",
                customer_id,
            )
            raise MTCustomerNotFound(f"No customer {customer_id!r} exists.")
        self.logger.warning(
            "%s put customer %s on %s billing. This applies to the next run "
            "and re-issues nothing.",
            actor,
            customer_id,
            periodicity.value if periodicity else "the agency's own",
        )
        self.logger.info(
            "Customer %s is billed %s.",
            customer_id,
            periodicity.value if periodicity else "as the agency bills",
        )
        return updated

    async def promote(self, customer_id: str) -> Customer:
        """Promote a prospect to an active customer.

        Args:
            customer_id (str): The customer to promote.

        Returns:
            Customer: The promoted customer.

        Raises:
            MTCustomerNotFound: If no such customer exists.
            MTCustomerNotPromotable: If they are not a prospect.

        Notes:
            - **This is the act that makes the planner start routing to their
              door.** A prospect may already hold accepted, priced work that
              every run has deliberately left out; promoting them is what puts it
              into the next one, so it is a named operation rather than one value
              among three on :meth:`set_status`.
            - Only from :attr:`~models.enums.RegistrationStatus.PROSPECT`.
              Promoting an active customer is refused rather than shrugged off:
              a control that silently succeeds without doing anything is one
              somebody presses twice. Reinstating a *stopped* customer is a
              different decision with different consequences, and it goes through
              :meth:`set_status` where it reads as what it is.
        """
        self.logger.debug("Reading customer %s before promoting them.", customer_id)  # noqa: E501
        existing = await self.get(customer_id)
        if existing.registration_status is not RegistrationStatus.PROSPECT:
            self.logger.warning(
                "Refused to promote customer %s: they are %s, not a prospect.",
                customer_id,
                existing.registration_status.value,
            )
            raise MTCustomerNotPromotable(
                f"Customer {customer_id!r} is "
                f"{existing.registration_status.value}, not a prospect. Only a "
                f"prospect can be promoted."
            )
        self.logger.info("Promoting prospect %s to an active customer.", customer_id)  # noqa: E501
        promoted = await self.customers.set_status(
            customer_id, RegistrationStatus.ACTIVE
        )
        if promoted is None:
            self.logger.error(
                "Customer %s vanished between the read and the promotion.",
                customer_id,
            )
            raise MTCustomerNotFound(f"No customer {customer_id!r} exists.")
        self.logger.info(
            "Customer %s is active. Their accepted work enters the next planning run.",
            customer_id,
        )
        return promoted

    async def quotes(self, customer_id: str) -> List[Quote]:
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
        """Remove a customer, and every quote written for them.

        Args:
            customer_id (str): The customer to remove.

        Raises:
            MTCustomerNotFound: If no such customer exists.

        Notes:
            - **The quotes go too.** They used to be a refusal: a customer with
              any quote could not be deleted at all, and the message suggested
              stopping them instead. Stopping is still the right answer for
              somebody who was really served and has really left — it keeps
              what was billed and who agreed to it — but it left no way at all
              to remove a household entered by mistake, or the fixtures a test
              campaign is obliged to clean up after itself. A quote names one
              customer and means nothing without them, so it cannot outlive
              them.
            - **This is irreversible and it destroys billing history**, which
              is why the count is logged at ``WARNING`` before anything is
              removed and why the screen that offers it says how many quotes
              and visits will go. A confirmation that does not say what it
              costs is a confirmation nobody reads.
            - The lines, the weekly aggregates and the scheduled visits follow
              their quote through the database's own cascades. The visits going
              is why a replan is queued afterwards, by the endpoint: the
              assistants who were due to make them now have gaps that other
              work can move into.
        """
        await self.get(customer_id)
        quotes = await self.quotes.list(customer_id=customer_id)
        if quotes:
            self.logger.warning(
                "Deleting customer %s also deletes %d quote(s) and everything "
                "scheduled from them. This cannot be undone.",
                customer_id,
                len(quotes),
            )
            for quote in quotes:
                if quote.id is None:
                    self.logger.error(
                        "A quote of customer %s carries no identifier and "
                        "cannot be deleted. The customer stays.",
                        customer_id,
                    )
                    raise MTCustomerHasQuotes(
                        f"Customer {customer_id!r} has a quote that cannot be "
                        f"identified, so it cannot be removed with them."
                    )
                await self.quotes.delete(quote.id)
            self.logger.info(
                "Deleted %d quote(s) of customer %s.", len(quotes), customer_id
            )
        await self._remove_portal_account(customer_id)
        removed = await self.customers.delete(customer_id)
        if not removed:
            self.logger.error(
                "Customer %s vanished between the read and the delete.",
                customer_id,
            )
            raise MTCustomerNotFound(f"No customer {customer_id!r} exists.")
        self.logger.info("Customer %s deleted.", customer_id)
