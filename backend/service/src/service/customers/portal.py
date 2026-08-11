from __future__ import annotations

# Standard library imports
from datetime import date
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third-party imports
from sqlalchemy.exc import SQLAlchemyError

# First-party imports
from models.enums import Language, QuoteStatus
from models.people.customer import Customer
from models.planning.intervention.intervention import Intervention
from models.quoting.quote import Quote
from models.schemas.requests.customers.customer_profile_update_request import (
    CustomerProfileUpdateRequest,
)
from models.billing.bill import Bill
from models.schemas.requests.billing.bill_filter import BillFilter
from service.billing.billings import BillingService
from service.customers.customers import CustomerService
from service.customers.exceptions import MTCustomerNotFound
from service.planning.interventions import InterventionService
from service.quotes.documents import QuoteDocumentService
from service.quotes.quotes import QuoteService
from storage.repositories.planning.intervention import InterventionRepository
from storage.repositories.quoting.quote import QuoteRepository


class CustomerPortalService:
    """Everything a household may do in their own space.

    Attributes:
        customers (CustomerService): Reads and edits the household's record.
        interventions (InterventionService): Cancels a visit and reprices.
        quotes (QuoteService): Moves a visit and reprices.
        quote_store (QuoteRepository): Sets the status back to validation.
        intervention_store (InterventionRepository): Reads the visits.
        bills (Optional[BillingService]): Reads and serves their invoices.
        documents (Optional[QuoteDocumentService]): Renders a quote as a PDF.
        logger (Logger): Logger for portal operations.

    Notes:
        - **Every method takes the household's identifier from the caller's
          credential**, never from a path parameter. The routes behind
          ``get_customer_user`` pass ``caller.customer_id``, which the account
          model guarantees is present, so there is no identifier a household
          could point at somebody else's file.
        - **This is a composition, not a reimplementation.** Cancelling already
          exists on :class:`~service.planning.interventions.InterventionService`
          and moving already exists on
          :class:`~service.quotes.quotes.QuoteService`; both reprice, and both
          were built for a manager. What this class adds is the one thing that
          differs when a *customer* does it: the quote goes back to
          :attr:`~models.enums.QuoteStatus.PENDING_VALIDATION`.
        - **Why the status moves here and not there.** A manager rescheduling
          answers *when* a piece of agreed work happens, so
          ``QuoteService.reschedule_line`` deliberately leaves the status alone
          — its docstring argues the point. A household rescheduling changes
          what the agency agreed to deliver, and that is a fact a manager has to
          see and re-approve. The same call, two meanings, and the difference
          belongs to the caller rather than to the operation.
        - **The consequence is real and the screen must say so.** Between the
          household's change and a manager re-validating, that work is scheduled
          nowhere: the planner only builds requirements from accepted quotes.
          Showing a silently empty calendar would be worse than showing nothing.
    """

    def __init__(
        self,
        customers: CustomerService,
        interventions: InterventionService,
        quotes: QuoteService,
        quote_store: QuoteRepository,
        intervention_store: InterventionRepository,
        bills: Optional[BillingService] = None,
        documents: Optional[QuoteDocumentService] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            customers (CustomerService): The customer service.
            interventions (InterventionService): The visit service.
            quotes (QuoteService): The quote service.
            quote_store (QuoteRepository): The quote store, for the status move.
            intervention_store (InterventionRepository): The visit store.
            bills (Optional[BillingService]): The billing service, needed only
                by the invoice routes.
            documents (Optional[QuoteDocumentService]): Renders a quote as a
                PDF, needed only by the quote download.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.customers = customers
        self.interventions = interventions
        self.quotes = quotes
        self.quote_store = quote_store
        self.intervention_store = intervention_store
        self.bills = bills
        self.documents = documents
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("CustomerPortalService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _own_intervention(
        self, customer_id: str, intervention_id: str
    ) -> Intervention:
        """Return a visit, refusing one that belongs to another household.

        Args:
            customer_id (str): The household making the request.
            intervention_id (str): The visit they named.

        Returns:
            Intervention: The visit.

        Raises:
            MTCustomerNotFound: If the visit does not exist, or is not theirs.

        Notes:
            **404 for both cases, and deliberately the same answer.** Telling
            "no such visit" apart from "not yours" would let somebody walk the
            identifier space and learn when the agency visits their neighbours —
            which is the same reasoning the assistant portfolio already applies
            to customers, recorded in ``docs/11-security.md``.
        """
        self.logger.debug(
            "Resolving visit %s for household %s.", intervention_id, customer_id
        )
        visit = await self.intervention_store.get(intervention_id)
        if visit is None:
            self.logger.warning(
                "Household %s named visit %s, which does not exist.",
                customer_id,
                intervention_id,
            )
            raise MTCustomerNotFound(f"No visit {intervention_id!r} exists.")
        if visit.customer_id != customer_id:
            self.logger.error(
                "Household %s tried to reach visit %s, which belongs to "
                "household %s; refused as not found.",
                customer_id,
                intervention_id,
                visit.customer_id,
            )
            raise MTCustomerNotFound(f"No visit {intervention_id!r} exists.")
        self.logger.info(
            "Visit %s belongs to household %s.", intervention_id, customer_id
        )
        return visit

    async def _send_back_for_validation(self, quote_id: str) -> None:
        """Return a quote to the manager's queue after a household changed it.

        Args:
            quote_id (str): The quote to move.

        Notes:
            - **The whole point of the customer-side change.** The household has
              altered what the agency agreed to deliver, so the agreement is no
              longer current and a manager has to look at it again.
            - Until they do, the work is scheduled nowhere: the planner builds
              requirements only from accepted quotes. That is the honest reading
              of "back to validation" and the reason the portal says so on
              screen rather than showing an empty calendar.
            - A quote already awaiting validation is left alone rather than
              written again — the move is idempotent, so two changes in a row do
              not produce two identical audit lines.
        """
        existing = await self.quote_store.get(quote_id)
        if existing is None:
            self.logger.error(
                "Quote %s vanished while it was being sent back for "
                "validation; the visit changed but the offer did not.",
                quote_id,
            )
            return
        if existing.status is QuoteStatus.PENDING_VALIDATION:
            self.logger.debug(
                "Quote %s already awaits validation; nothing to move.",
                existing.reference,
            )
            return
        self.logger.warning(
            "Quote %s goes from %s back to pending-validation: the household "
            "changed it, so nothing on it is planned until a manager agrees.",
            existing.reference,
            existing.status.value,
        )
        await self.quote_store.set_status(quote_id, QuoteStatus.PENDING_VALIDATION)
        self.logger.info("Quote %s awaits validation.", existing.reference)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def profile(self, customer_id: str) -> Customer:
        """Return the household's own record.

        Args:
            customer_id (str): The household, from the credential.

        Returns:
            Customer: Their record.

        Raises:
            MTCustomerNotFound: If the linked record no longer exists.
        """
        self.logger.debug("Reading the profile of household %s.", customer_id)
        try:
            customer = await self.customers.get(customer_id)
        except SQLAlchemyError:
            self.logger.error("Reading household %s failed.", customer_id)
            raise
        if not customer.address.is_geocoded():
            self.logger.warning(
                "Household %s has no coordinate; nothing can be planned for "
                "them until the address resolves.",
                customer_id,
            )
        self.logger.info("Serving the profile of household %s.", customer_id)
        return customer

    async def update_profile(
        self, customer_id: str, payload: CustomerProfileUpdateRequest
    ) -> Customer:
        """Correct the household's own contact details.

        Args:
            customer_id (str): The household, from the credential.
            payload (CustomerProfileUpdateRequest): The new contact block.

        Returns:
            Customer: The updated record.

        Raises:
            MTCustomerNotFound: If the linked record no longer exists.

        Notes:
            - **The stored record is the base, and only the payload's fields are
              replaced.** The status and the billing periodicity are carried
              over from what is stored rather than taken from the request —
              which is the second of two gates, the first being that the request
              model has no field for either.
            - The address re-geocodes during validation, so a household
              correcting a mistyped street is the fastest route to their work
              being planned to the right door.
        """
        self.logger.info("Household %s is correcting their details.", customer_id)
        existing = await self.customers.get(customer_id)
        self.logger.debug(
            "Preserving status=%s periodicity=%s across the edit.",
            existing.registration_status.value,
            existing.billing_periodicity,
        )
        updated = existing.model_copy(
            update={
                "first_name": payload.first_name,
                "last_name": payload.last_name,
                "phone_number": payload.phone_number,
                "email": payload.email,
                "address": payload.address,
            }
        )
        if not updated.address.is_geocoded():
            self.logger.warning(
                "The address household %s just saved does not resolve (%s); "
                "their work cannot be planned until it does.",
                customer_id,
                updated.address.geocoding_error,
            )
        try:
            stored = await self.customers.update(customer_id, updated)
        except SQLAlchemyError:
            self.logger.error("Saving household %s failed.", customer_id)
            raise
        return stored

    async def planning(
        self, customer_id: str, period_start: date, period_end: date
    ) -> List[Intervention]:
        """Return the household's visits over a period.

        Args:
            customer_id (str): The household, from the credential.
            period_start (date): First day of interest, inclusive.
            period_end (date): Last day of interest, inclusive.

        Returns:
            List[Intervention]: Their visits, in day and time order.

        Notes:
            Scoped in the statement by
            :meth:`~storage.repositories.planning.intervention.InterventionRepository.list_for_customer`,
            not filtered afterwards — a page narrowed after the fact has already
            read visits belonging to other households.
        """
        self.logger.debug(
            "Reading visits of household %s from %s to %s.",
            customer_id,
            period_start,
            period_end,
        )
        if period_end < period_start:
            self.logger.error(
                "Household %s asked for %s to %s, which is backwards; no visit "
                "can fall inside it.",
                customer_id,
                period_start,
                period_end,
            )
        visits = await self.intervention_store.list_for_customer(
            customer_id, period_start, period_end
        )
        if not visits:
            self.logger.warning(
                "Household %s has no visit between %s and %s.",
                customer_id,
                period_start,
                period_end,
            )
        self.logger.info(
            "Serving %d visit(s) to household %s.", len(visits), customer_id
        )
        return visits

    async def quotes_for(self, customer_id: str) -> List[Quote]:
        """Return every quote written for the household.

        Args:
            customer_id (str): The household, from the credential.

        Returns:
            List[Quote]: Their quotes, newest first.

        Raises:
            MTCustomerNotFound: If the linked record no longer exists.
        """
        self.logger.debug("Reading the quotes of household %s.", customer_id)
        try:
            quotes = await self.customers.quotes_for(customer_id)
        except SQLAlchemyError:
            self.logger.error("Reading quotes of household %s failed.", customer_id)
            raise
        if not quotes:
            self.logger.warning("Household %s has never been quoted.", customer_id)
        self.logger.info(
            "Serving %d quote(s) to household %s.", len(quotes), customer_id
        )
        return quotes

    async def cancel_visit(
        self, customer_id: str, intervention_id: str
    ) -> Optional[Quote]:
        """Cancel one visit, and send its quote back for validation.

        Args:
            customer_id (str): The household, from the credential.
            intervention_id (str): The visit to cancel.

        Returns:
            Optional[Quote]: The repriced quote, or ``None`` when that visit was
            the only thing on it and the quote went with it.

        Raises:
            MTCustomerNotFound: If the visit does not exist, or is not theirs.

        Notes:
            - **The line goes, not just the visit**, because
              :meth:`~service.planning.interventions.InterventionService.delete`
              says so: the next run rebuilds the period from the quote lines, so
              a visit removed on its own reappears within the hour.
            - A quote whose last line is cancelled is deleted with it, and there
              is then nothing to send back for validation — which is why the
              return is optional and the status move is skipped.
        """
        visit = await self._own_intervention(customer_id, intervention_id)
        self.logger.warning(
            "Household %s is cancelling their visit on %s (%s).",
            customer_id,
            visit.day,
            visit.name,
        )
        try:
            quote = await self.interventions.delete(intervention_id)
        except SQLAlchemyError:
            self.logger.error("Cancelling visit %s failed.", intervention_id)
            raise
        if quote is None or quote.id is None:
            self.logger.info(
                "The cancelled visit was the last on its quote; the quote went "
                "with it and there is nothing to re-validate."
            )
            return quote
        await self._send_back_for_validation(quote.id)
        return await self.quote_store.get(quote.id)

    async def reschedule_visit(
        self,
        customer_id: str,
        intervention_id: str,
        day: date,
        start_minute: int,
        end_minute: int,
    ) -> Quote:
        """Move one visit, and send its quote back for validation.

        Args:
            customer_id (str): The household, from the credential.
            intervention_id (str): The visit to move.
            day (date): The day it should happen on instead.
            start_minute (int): Earliest it may begin, minutes from midnight.
            end_minute (int): Latest it may finish, in the same units.

        Returns:
            Quote: The repriced quote, awaiting validation.

        Raises:
            MTCustomerNotFound: If the visit does not exist, or is not theirs.
            MTQuoteNotFound: If no quote carries the visit's line.
            MTQuoteLineWindowTooShort: If the window is narrower than the work.

        Notes:
            - **It reprices.** A visit moved onto a Sunday or a public holiday
              costs more; the surcharge is a property of the day. The household
              therefore cannot move work without the agency seeing the new
              price, which is a second reason the quote returns to validation.
            - The move itself is
              :meth:`~service.quotes.quotes.QuoteService.reschedule_line`,
              unchanged. Only the status afterwards differs.
        """
        visit = await self._own_intervention(customer_id, intervention_id)
        self.logger.warning(
            "Household %s is moving their visit on %s to %s (%d–%d).",
            customer_id,
            visit.day,
            day,
            start_minute,
            end_minute,
        )
        # A visit names its line, not its quote — so the quote is resolved the
        # way the calendar's own edits resolve it, through the line.
        sold_on = await self.quotes.get_by_line(visit.quote_line_id)
        try:
            quote = await self.quotes.reschedule_line(
                quote_id=sold_on.id or "",
                quote_line_id=visit.quote_line_id,
                day=day,
                start_minute=start_minute,
                end_minute=end_minute,
            )
        except SQLAlchemyError:
            self.logger.error("Moving visit %s failed.", intervention_id)
            raise
        if quote.id is not None:
            await self._send_back_for_validation(quote.id)
            refreshed = await self.quote_store.get(quote.id)
            if refreshed is not None:
                return refreshed
        self.logger.error(
            "Quote %s carries no identifier after the move; its status could "
            "not be sent back for validation.",
            quote.reference,
        )
        return quote

    async def bills_for(self, customer_id: str, company_id: str) -> List[Bill]:
        """Return every invoice issued to the household.

        Args:
            customer_id (str): The household, from the credential.
            company_id (str): The agency, from the credential.

        Returns:
            List[Bill]: Their invoices, most recent period first.

        Notes:
            **Narrowed in the query by a ``BillFilter``**, not filtered
            afterwards. A page of an agency's invoices narrowed after the fact
            has already read other households' figures — and an invoice carries
            a name, an address and what somebody pays for care.
        """
        self.logger.debug("Reading the invoices of household %s.", customer_id)
        if self.bills is None:
            self.logger.error(
                "No billing service is wired in; household %s is shown no "
                "invoices at all rather than an error.",
                customer_id,
            )
            return []
        invoices = await self.bills.list(
            company_id=company_id,
            size=200,
            bill_filter=BillFilter(customer_id=customer_id),
        )
        if not invoices:
            self.logger.warning("Household %s has never been invoiced.", customer_id)
        self.logger.info(
            "Serving %d invoice(s) to household %s.", len(invoices), customer_id
        )
        return invoices

    async def bill_document(self, customer_id: str, bill_id: str) -> Tuple[bytes, str]:
        """Return one of the household's invoices as a PDF.

        Args:
            customer_id (str): The household, from the credential.
            bill_id (str): The invoice they asked for.

        Returns:
            Tuple[bytes, str]: The document, and its filename.

        Raises:
            MTCustomerNotFound: If the invoice is not theirs, or does not
                exist — **the same answer for both**, so nobody can walk the
                identifier space and learn what the agency has billed others.

        Notes:
            The ownership check is here rather than on the billing service,
            because that service answers a manager who is entitled to every
            invoice. The narrowing belongs to the caller.
        """
        self.logger.debug("Household %s asked for invoice %s.", customer_id, bill_id)
        if self.bills is None:
            self.logger.error("No billing service is wired in; invoice refused.")
            raise MTCustomerNotFound(f"No invoice {bill_id!r} exists.")
        invoice = await self.bills.get(bill_id)
        if invoice.customer_id != customer_id:
            self.logger.error(
                "Household %s asked for invoice %s, which belongs to household "
                "%s; refused as not found.",
                customer_id,
                bill_id,
                invoice.customer_id,
            )
            raise MTCustomerNotFound(f"No invoice {bill_id!r} exists.")
        self.logger.info(
            "Serving invoice %s to household %s.", invoice.number, customer_id
        )
        return await self.bills.document(bill_id)

    async def quote_document(
        self, customer_id: str, quote_id: str, language: Language
    ) -> Tuple[bytes, str]:
        """Return one of the household's quotes as a PDF.

        Args:
            customer_id (str): The household, from the credential.
            quote_id (str): The quote they asked for.
            language (Language): The language they read.

        Returns:
            Tuple[bytes, str]: The document, and its filename.

        Raises:
            MTCustomerNotFound: If the quote is not theirs, or does not exist.
            MTQuoteNotPriced: If it has never been priced.

        Notes:
            Written in the **household's** language, not the agency's. The same
            document downloaded by a manager comes out in theirs — it is the
            same offer, addressed to two different readers.
        """
        self.logger.debug("Household %s asked for quote %s.", customer_id, quote_id)
        if self.documents is None:
            self.logger.error("No document service is wired in; quote refused.")
            raise MTCustomerNotFound(f"No quote {quote_id!r} exists.")
        quote = await self.quotes.get(quote_id)
        if quote.customer_id != customer_id:
            self.logger.error(
                "Household %s asked for quote %s, which belongs to household "
                "%s; refused as not found.",
                customer_id,
                quote_id,
                quote.customer_id,
            )
            raise MTCustomerNotFound(f"No quote {quote_id!r} exists.")
        self.logger.info(
            "Serving quote %s to household %s in %s.",
            quote.reference,
            customer_id,
            language.value,
        )
        return await self.documents.document(quote_id, language=language)
