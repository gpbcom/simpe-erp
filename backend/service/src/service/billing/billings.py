from __future__ import annotations

# Standard library imports
from datetime import UTC, date, datetime
from decimal import Decimal
from logging import Logger, getLogger
from typing import Dict, List, Optional, Tuple

# Third-party imports
from sqlalchemy.exc import IntegrityError

# First-party imports
from models.billing.bill import Bill
from models.billing.bill_line import BillLine
from models.billing.billing_run import BillingRun
from models.companies.company import Company
from models.configuration.billing_config import BillingConfig
from models.enums import BillingRunStatus, BillStatus, Language
from models.people.customer import Customer
from models.planning.intervention import Intervention
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from models.schemas.requests.billing.bill_filter import BillFilter
from models.schemas.requests.billing.billing_settings_request import (
    BillingSettingsRequest,
)
from models.settings.billing_settings import BillingSettings
from service.billing.exceptions import (
    MTBillAlreadyIssued,
    MTBillDocumentStorageUnavailable,
    MTBillDocumentUnavailable,
    MTBillingPeriodInFuture,
    MTBillingRunNotFound,
    MTBillingSettingsUnavailable,
    MTBillNotFound,
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
from storage.s3.exceptions import MTInvalidS3StorageException
from storage.s3.s3_storage import S3Storage


class BillingService:
    """Turns delivered care into invoices, and tracks them through to payment.

    Attributes:
        bills (BillRepository): Where invoices are stored.
        runs (BillingRunRepository): Where generation runs are recorded.
        settings (BillingSettingsRepository): The agency's invoicing rules.
        quotes (QuoteRepository): Where the prices come from.
        interventions (InterventionRepository): Where the delivered hours come
            from.
        customers (CustomerRepository): Who invoices are addressed to.
        companies (CompanyRepository): Who issues them.
        documents (Optional[S3Storage]): Where rendered documents are kept.
        renderer (InvoiceRenderer): Lays a bill out as a PDF.
        config (BillingConfig): The rules a deployment starts with.
        logger (Logger): Logger for billing operations.

    Notes:
        - **Nothing here re-prices anything.** The money on a charge is copied
          from the quote line that sold it, so an invoice reprints identically
          after the catalogue is repriced. A customer is not re-billed for work
          already quoted, and that is a property of this service rather than a
          discipline its callers have to keep.
        - **A generation run sends nothing.** It renders every document and
          stops, leaving each invoice waiting for a manager. Approval is what
          puts one in a customer's inbox — see
          :meth:`set_status` and :class:`~service.billing.webhook.BillingWebhook`.
        - The invoicing rules live here rather than in a service of their own,
          the way the planning rules live on ``PlanningService``: one service
          per entity, and the rules have no life apart from the invoices they
          are printed on.
    """

    def __init__(
        self,
        bills: BillRepository,
        runs: BillingRunRepository,
        settings: BillingSettingsRepository,
        quotes: QuoteRepository,
        interventions: InterventionRepository,
        customers: CustomerRepository,
        companies: CompanyRepository,
        config: BillingConfig,
        documents: Optional[S3Storage] = None,
        renderer: Optional[InvoiceRenderer] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            bills (BillRepository): Where invoices are stored.
            runs (BillingRunRepository): Where generation runs are recorded.
            settings (BillingSettingsRepository): The invoicing rules.
            quotes (QuoteRepository): Where the prices come from.
            interventions (InterventionRepository): Where the hours come from.
            customers (CustomerRepository): Who invoices are addressed to.
            companies (CompanyRepository): Who issues them.
            config (BillingConfig): The rules a deployment starts with.
            documents (Optional[S3Storage]): Where documents are kept. A
                deployment without one cannot issue invoices, and says so when
                asked to rather than at import.
            renderer (Optional[InvoiceRenderer]): Lays a bill out as a PDF.
                Defaults to a renderer sharing this service's logger.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.bills = bills
        self.runs = runs
        self.settings = settings
        self.quotes = quotes
        self.interventions = interventions
        self.customers = customers
        self.companies = companies
        self.config = config
        self.documents = documents
        self.logger = logger if logger else getLogger(__name__)
        self.renderer = renderer if renderer else InvoiceRenderer()
        self.logger.debug(
            "BillingService created (documents=%s).",
            "configured" if documents else "unavailable",
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _require_documents(self) -> S3Storage:
        """Return the object store, refusing when none is configured.

        Returns:
            S3Storage: The configured store.

        Raises:
            MTBillDocumentStorageUnavailable: If no store was injected.

        Notes:
            Checked before a number is allocated, never after. An invoice whose
            document could not be stored would leave a burnt number behind, and
            the series cannot explain a gap.
        """
        if self.documents is None:
            self.logger.error(
                "No object store is configured; invoices cannot be issued "
                "because there is nowhere to keep their documents."
            )
            raise MTBillDocumentStorageUnavailable(
                "No document store is configured for invoices."
            )
        return self.documents

    async def _logo_of(self, company: Company) -> Optional[bytes]:
        """Return an agency's logo, when there is one to read.

        Args:
            company (Company): The agency issuing the invoice.

        Returns:
            Optional[bytes]: The image bytes, or ``None``.

        Notes:
            Every failure is a ``None``. A document without its letterhead is
            still a legally complete invoice, and refusing to issue one over a
            decoration would be the wrong trade — the same rule
            :meth:`~service.emails.emails.EmailService._fetch_logo` keeps.
        """
        if self.documents is None or not company.logo_url:
            return None
        try:
            return await self.documents.fetch_logo(company.logo_url)
        except MTInvalidS3StorageException as exc:
            self.logger.warning(
                "Could not read the logo of agency %s (%s); the invoice will "
                "print without it.",
                company.name,
                exc,
            )
            return None

    def _charge_from(self, line: QuoteLine, visit: Optional[Intervention]) -> BillLine:  # noqa: E501
        """Build one charge from a sold line and the visit that delivered it.

        Args:
            line (QuoteLine): The quote line being charged.
            visit (Optional[Intervention]): The visit that delivered it, when a
                planning run ever placed one.

        Returns:
            BillLine: The charge.

        Notes:
            - **The amounts are copied, never recomputed.** A rate that has
              moved in the catalogue since the quote was written must not reach
              an invoice for work sold before it moved.
            - The VAT rate is read from the line's category **now** and stored,
              so a reprint after a statutory change still shows what the
              customer was charged.
            - The delivered day, hours and assistant are copied off the visit
              rather than joined to it: re-planning a period deletes every
              intervention in it, and an invoice must survive that.
        """
        return BillLine(
            quote_line_id=line.id,
            intervention_id=visit.id if visit else None,
            name=line.name,
            service_category=line.service_category,
            service_date=line.service_date,
            day=visit.day if visit else None,
            start_time=visit.start_time if visit else None,
            end_time=visit.end_time if visit else None,
            hca_full_name=visit.hca_full_name if visit else None,
            duration_minutes=line.duration_minutes,
            hourly_rate_ht=line.hourly_rate_ht,
            total_ht=line.total_ht,
            vat_rate=line.service_category.vat_rate(),
            vat_amount=line.vat_amount,
            total_ttc=line.total_ttc,
        )

    async def _render_and_store(
        self,
        bill: Bill,
        customer: Customer,
        company: Company,
        settings: BillingSettings,
        language: Language,
    ) -> str:
        """Render an invoice and put its document in the store.

        Args:
            bill (Bill): The invoice to render.
            customer (Customer): The customer it is addressed to.
            company (Company): The agency issuing it.
            settings (BillingSettings): The terms it is issued under.
            language (Language): The language to write it in.

        Returns:
            str: The object key the document was written under.

        Raises:
            MTInvoiceRenderFailed: If the document could not be laid out.
            MTS3UploadFailed: If it could not be stored.

        Notes:
            **The language is passed in, not read off the customer.** A customer
            record carries no language preference — only an account does — and
            reaching for one that does not exist would silently print every
            invoice in French while looking as though it had asked. The caller
            supplies the language of whoever asked for the run, which is exactly
            what :meth:`~service.emails.emails.EmailService.send_quotes` does
            with a batch of quotes and for the same reason.
        """
        documents = self._require_documents()
        logo = await self._logo_of(company)
        payload = self.renderer.render(
            bill=bill,
            customer=customer,
            company=company,
            settings=settings,
            language=language,
            logo=logo,
        )
        return await documents.upload_invoice(
            company.id or bill.company_id, bill.number, payload
        )

    async def _billable_customers(
        self, company_id: str, period_start: date, period_end: date
    ) -> List[str]:
        """Return the customers with sold work inside a period.

        Args:
            company_id (str): The agency doing the billing.
            period_start (date): First day of the window, inclusive.
            period_end (date): Last day of the window, inclusive.

        Returns:
            List[str]: The customers to bill, each once, in a stable order.

        Notes:
            Read off the accepted quotes rather than off the customer book: a
            customer with no work in the period is not somebody the run passed
            over, it is somebody the run never had a reason to look at. Ordered
            so two runs over one period do the same work in the same sequence,
            which is what makes a partial run's failure list comparable between
            attempts.
        """
        quotes = await self.quotes.list_schedulable(
            company_id, period_start, period_end
        )
        customer_ids: List[str] = []
        for quote in quotes:
            if quote.customer_id not in customer_ids:
                customer_ids.append(quote.customer_id)
        self.logger.info(
            "%d customer(s) have billable work for agency %s between %s and %s.",
            len(customer_ids),
            company_id,
            period_start,
            period_end,
        )
        if not customer_ids:
            self.logger.warning(
                "No accepted quote of agency %s covers %s..%s; the run will "
                "issue no invoice.",
                company_id,
                period_start,
                period_end,
            )
        return sorted(customer_ids)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def current_settings(self) -> BillingSettings:
        """Return the agency's invoicing rules, seeding them on first read.

        Returns:
            BillingSettings: The stored rules.

        Raises:
            MTBillingSettingsUnavailable: If the rules can neither be read nor
                seeded.

        Notes:
            Seeded from the configuration file the first time anybody asks, the
            way the planning rules are. Without them there are no payment terms
            to print, and an invoice missing those is non-conforming — so this
            raises rather than inventing a default at the point of rendering.
        """
        self.logger.debug("Reading the billing settings.")
        stored = await self.settings.get()
        if stored is not None:
            return stored
        self.logger.info(
            "The billing settings are not seeded; writing the configured defaults."
        )
        seeded = await self.settings.seed(self.config.to_settings())
        if seeded is None:
            self.logger.error(
                "The billing settings could not be seeded; no invoice can "
                "state its payment terms."
            )
            raise MTBillingSettingsUnavailable("The billing settings are unavailable.")
        return seeded

    async def update_settings(
        self, request: BillingSettingsRequest, actor: str
    ) -> BillingSettings:
        """Change the agency's invoicing rules.

        Args:
            request (BillingSettingsRequest): The whole rule set.
            actor (str): The account making the change.

        Returns:
            BillingSettings: The stored rules.

        Raises:
            MTBillingSettingsUnavailable: If the rules are not seeded.

        Notes:
            A change applies to the **next** generation run. An invoice already
            issued keeps the terms it was printed with, because the terms are
            part of what the customer was told and not a live lookup — which is
            why this logs at warning: it is a change to what customers are told.
        """
        existing = await self.current_settings()
        updated = await self.settings.update(request.apply_to(existing, actor))
        if updated is None:
            self.logger.error("The billing settings could not be updated by %s.", actor)
            raise MTBillingSettingsUnavailable("The billing settings are unavailable.")
        self.logger.warning(
            "%s changed the invoicing rules to %s billing with %d-day terms; "
            "this applies to the next run and re-issues nothing.",
            actor,
            updated.periodicity.value,
            updated.payment_terms_days,
        )
        return updated

    async def window_for(self, reference_date: date) -> Tuple[date, date]:
        """Return the billing window containing a day, under the stored rules.

        Args:
            reference_date (date): Any day inside the wanted period.

        Returns:
            Tuple[date, date]: The period's first and last day, both inclusive.
        """
        settings = await self.current_settings()
        window = settings.window_for(reference_date)
        self.logger.debug(
            "%s falls in the %s window %s..%s.",
            reference_date,
            settings.periodicity.value,
            window[0],
            window[1],
        )
        return window

    async def request_run(
        self, company_id: str, reference_date: date, requested_by: str
    ) -> BillingRun:
        """Record a request to bill the period containing a day.

        Args:
            company_id (str): The agency whose customers are being billed.
            reference_date (date): Any day inside the period to bill.
            requested_by (str): The account asking for it.

        Returns:
            BillingRun: The queued run, carrying the identifier to poll.

        Raises:
            MTBillingPeriodInFuture: If the period has not finished yet.

        Notes:
            - The record is written **before** the work is queued, so the
              identifier handed back is real even when the broker is
              unreachable. The run simply stays pending.
            - A period still running is refused rather than billed early. Care
              that has not happened cannot be invoiced, and an empty document
              would carry a number the series can never reuse.
        """
        settings = await self.current_settings()
        period_start, period_end = settings.window_for(reference_date)
        today = datetime.now(UTC).date()
        if period_end >= today:
            self.logger.warning(
                "Refusing to bill %s..%s for agency %s: the period has not "
                "finished (today is %s).",
                period_start,
                period_end,
                company_id,
                today,
            )
            raise MTBillingPeriodInFuture(
                f"The period {period_start}..{period_end} has not finished; "
                f"care that has not happened cannot be invoiced."
            )
        self.logger.info(
            "%s asked for agency %s to be billed for %s..%s.",
            requested_by,
            company_id,
            period_start,
            period_end,
        )
        return await self.runs.create(
            BillingRun(
                company_id=company_id,
                requested_by=requested_by,
                periodicity=settings.periodicity,
                reference_date=reference_date,
                period_start=period_start,
                period_end=period_end,
                requested_at=datetime.now(UTC),
            )
        )

    async def collect_lines(
        self,
        company_id: str,
        customer_id: str,
        period_start: date,
        period_end: date,
    ) -> List[BillLine]:
        """Return the charges a customer owes for a period.

        Args:
            company_id (str): The agency doing the billing.
            customer_id (str): The customer being billed.
            period_start (date): First day of the window, inclusive.
            period_end (date): Last day of the window, inclusive.

        Returns:
            List[BillLine]: The charges, one per delivered service.

        Notes:
            - **This is the whole of the time pro-rata.** A quote line carries
              one ``service_date``, not a range: it is a single dated visit. No
              line can straddle a period boundary, so "only the part inside the
              window is billed" reduces to a date filter and **no fractional
              amount is computed anywhere**. Lines dated after the window are
              simply absent; the next period has a different window and picks
              them up unchanged. A quote running March to June under monthly
              billing produces four invoices whose totals sum to the quote's.
            - ``effective_lines`` supplies the other half for free: it drops
              anything after ``interrupted_on``, inclusive, so an interrupted
              arrangement stops billing on the day it stopped being delivered.
            - An unpriced line is **dropped and reported at error**, never
              zeroed. A bill line requires its money, and charging nothing for
              delivered care would be a loss nobody notices.
            - A line with no matching visit is still billed. The work was sold
              and delivered whether or not a planning run ever placed it, and
              dropping it would silently forgive money the agency earned.
        """
        self.logger.debug(
            "Collecting the charges of customer %s for %s..%s.",
            customer_id,
            period_start,
            period_end,
        )
        quotes: List[Quote] = await self.quotes.list_schedulable(
            company_id, period_start, period_end
        )
        visits = await self.interventions.list_for_customer(
            customer_id, period_start, period_end
        )
        by_line: Dict[str, Intervention] = {
            visit.quote_line_id: visit for visit in visits
        }
        charges: List[BillLine] = []
        for quote in quotes:
            if quote.customer_id != customer_id:
                continue
            for line in quote.effective_lines():
                if not period_start <= line.service_date <= period_end:
                    continue
                if not line.is_priced():
                    self.logger.error(
                        "Quote %s line %s (%s on %s) has no price and cannot "
                        "be billed; it is left off the invoice.",
                        quote.reference,
                        line.id,
                        line.name,
                        line.service_date,
                    )
                    continue
                charges.append(self._charge_from(line, by_line.get(line.id or "")))
        if not charges:
            self.logger.warning(
                "Customer %s has nothing billable between %s and %s.",
                customer_id,
                period_start,
                period_end,
            )
        self.logger.info(
            "Collected %d charge(s) for customer %s.", len(charges), customer_id
        )
        return charges

    async def generate_for_customer(
        self,
        company_id: str,
        customer_id: str,
        period_start: date,
        period_end: date,
        run_id: Optional[str] = None,
        generated_by: Optional[str] = None,
        language: Language = Language.FR,
    ) -> Optional[Bill]:
        """Write one customer's invoice for a period, if they owe anything.

        Args:
            company_id (str): The agency issuing it.
            customer_id (str): The customer being billed.
            period_start (date): First day of the window, inclusive.
            period_end (date): Last day of the window, inclusive.
            run_id (Optional[str]): The run producing it.
            generated_by (Optional[str]): The account that asked for the run.
            language (Language): The language to write the document in.
                Defaults to French, which is the agency's own.

        Returns:
            Optional[Bill]: The invoice, or ``None`` when there was nothing to
            bill or the period was billed already.

        Raises:
            MTBillDocumentStorageUnavailable: If no object store is configured.
            MTInvoiceRenderFailed: If the document could not be laid out.

        Notes:
            - **Three guards against billing a customer twice**, and they are not
              redundant: the ``exists_for_period`` check makes a re-run a reported
              no-op, the unique index makes it safe when two runs race past that
              check, and the loser of such a race re-reads the winner's invoice
              rather than failing. Only the middle one is a guarantee.
            - The document is rendered and stored **before** the record is
              written, so a failure anywhere leaves no row pointing at a document
              that does not exist. The number is allocated first because the
              document has to print it.
        """
        if await self.bills.exists_for_period(customer_id, period_start, period_end):  # noqa: E501
            self.logger.info(
                "Customer %s is already billed for %s..%s; skipping.",
                customer_id,
                period_start,
                period_end,
            )
            return None
        charges = await self.collect_lines(
            company_id, customer_id, period_start, period_end
        )
        if not charges:
            self.logger.info(
                "Customer %s owes nothing for %s..%s; no invoice is issued.",
                customer_id,
                period_start,
                period_end,
            )
            return None

        customer = await self.customers.get(customer_id)
        company = await self.companies.get(company_id)
        if customer is None or company is None:
            self.logger.error(
                "Cannot bill customer %s for agency %s: the customer or the "
                "agency no longer exists.",
                customer_id,
                company_id,
            )
            raise MTBillNotFound(
                f"Customer {customer_id!r} or agency {company_id!r} is gone."
            )

        settings = await self.current_settings()
        issued_on = datetime.now(UTC).date()
        sequence, number = await self.bills.next_number(company_id, issued_on.year)  # noqa: E501
        draft = Bill(
            company_id=company_id,
            customer_id=customer_id,
            billing_run_id=run_id,
            number=number,
            sequence=sequence,
            sequence_year=issued_on.year,
            periodicity=settings.periodicity,
            period_start=period_start,
            period_end=period_end,
            issued_on=issued_on,
            due_on=settings.due_date_for(issued_on),
            customer_full_name=customer.full_name(),
            customer_address=customer.address,
            lines=charges,
            total_ht=sum((line.total_ht for line in charges), Decimal("0.00")),
            total_vat=sum((line.vat_amount for line in charges), Decimal("0.00")),  # noqa: E501
            total_ttc=sum((line.total_ttc for line in charges), Decimal("0.00")),  # noqa: E501
            generated_by=generated_by,
        )
        document_key = await self._render_and_store(
            draft, customer, company, settings, language
        )
        try:
            stored = await self.bills.create(
                draft.model_copy(update={"document_key": document_key})
            )
        except IntegrityError:
            self.logger.warning(
                "Another run billed customer %s for %s..%s first; keeping "
                "theirs and discarding %s.",
                customer_id,
                period_start,
                period_end,
                number,
            )
            return None
        self.logger.info(
            "Issued invoice %s to customer %s for %s TTC.",
            stored.number,
            customer_id,
            stored.total_ttc,
        )
        return stored

    async def execute_run(self, run_id: str) -> BillingRun:
        """Bill every customer with work in a run's period.

        Args:
            run_id (str): The run to execute.

        Returns:
            BillingRun: The finished run.

        Raises:
            MTBillingRunNotFound: If no such run exists.

        Notes:
            Each customer is billed inside its own guard, so one bad record
            costs one invoice rather than the month. A run that billed some and
            failed on others finishes **partial** and names the customers it
            could not bill — which is the only thing that makes such a run
            actionable.
        """
        run = await self.runs.get(run_id)
        if run is None:
            self.logger.error("No billing run found with id %s.", run_id)
            raise MTBillingRunNotFound(f"No billing run {run_id!r}.")
        self.logger.info(
            "Executing billing run %s over %s..%s.",
            run_id,
            run.period_start,
            run.period_end,
        )
        await self.runs.mark_running(run_id, datetime.now(UTC))

        written: List[str] = []
        failed: List[str] = []
        for customer_id in await self._billable_customers(
            run.company_id, run.period_start, run.period_end
        ):
            try:
                issued = await self.generate_for_customer(
                    company_id=run.company_id,
                    customer_id=customer_id,
                    period_start=run.period_start,
                    period_end=run.period_end,
                    run_id=run_id,
                    generated_by=run.requested_by,
                )
            except Exception as exc:  # noqa: BLE001 - one customer, not the run
                self.logger.error(
                    "Could not bill customer %s in run %s: %s.",
                    customer_id,
                    run_id,
                    exc,
                )
                failed.append(customer_id)
                continue
            if issued is not None and issued.id is not None:
                written.append(issued.id)

        status = BillingRunStatus.SUCCEEDED
        if failed and written:
            status = BillingRunStatus.PARTIAL
        elif failed:
            status = BillingRunStatus.FAILED
        finished = await self.runs.mark_finished(
            run_id,
            status,
            datetime.now(UTC),
            bill_ids=written,
            failed_customer_ids=failed,
            error=None if not failed else "Some customers could not be billed.",
        )
        if finished is None:
            self.logger.error(
                "Billing run %s vanished while it was being executed.", run_id
            )
            raise MTBillingRunNotFound(f"No billing run {run_id!r}.")
        return finished

    async def get(self, bill_id: str) -> Bill:
        """Return one invoice.

        Args:
            bill_id (str): The invoice to read.

        Returns:
            Bill: The invoice.

        Raises:
            MTBillNotFound: If no such invoice exists.
        """
        self.logger.debug("Reading bill %s.", bill_id)
        bill = await self.bills.get(bill_id)
        if bill is None:
            self.logger.warning("No bill found with id %s.", bill_id)
            raise MTBillNotFound(f"No bill {bill_id!r}.")
        return bill

    async def list(
        self,
        company_id: str,
        page: int = 1,
        size: Optional[int] = None,
        bill_filter: Optional[BillFilter] = None,
    ) -> List[Bill]:
        """Return a page of an agency's invoices.

        Args:
            company_id (str): The agency whose invoices are being read.
            page (int): One-based page number.
            size (Optional[int]): Page size.
            bill_filter (Optional[BillFilter]): The screen's filter.

        Returns:
            List[Bill]: The matching invoices.
        """
        self.logger.debug("Listing the bills of agency %s.", company_id)
        return await self.bills.list(
            page=page,
            size=size,
            company_id=company_id,
            bill_filter=bill_filter,
        )

    async def count(
        self, company_id: str, bill_filter: Optional[BillFilter] = None
    ) -> int:
        """Return how many of an agency's invoices match a filter.

        Args:
            company_id (str): The agency whose invoices are being counted.
            bill_filter (Optional[BillFilter]): The screen's filter.

        Returns:
            int: The number of matching invoices.
        """
        return await self.bills.count(company_id=company_id, bill_filter=bill_filter)

    async def set_status(self, bill_id: str, target: BillStatus, actor: str) -> Bill:
        """Move an invoice along its commercial lifecycle.

        Args:
            bill_id (str): The invoice to move.
            target (BillStatus): The status to move it to.
            actor (str): The manager or administrator making the change.

        Returns:
            Bill: The updated invoice.

        Raises:
            MTBillNotFound: If no such invoice exists.
            MTBillTransitionNotAllowed: If the move skips a step.

        Notes:
            - **The lifecycle is decided here**, against the invoice's *current*
              status, never against what a screen believed it to be. A row
              rendered a minute ago may have moved since, and a client cannot be
              trusted to have re-read it.
            - Reaching :attr:`~models.enums.BillStatus.ACCEPTED` is what sends
              the invoice: the endpoint publishes ``bill.accepted`` after this
              returns, and the webhook that consumes it does the emailing. That
              ordering matters — nothing leaves the building until the record
              says a human approved it.
        """
        bill = await self.get(bill_id)
        if not bill.status.can_move_to(target):
            self.logger.warning(
                "%s tried to move bill %s from %s to %s, which skips a step.",
                actor,
                bill.number,
                bill.status.value,
                target.value,
            )
            raise MTBillTransitionNotAllowed(
                f"A bill in {bill.status.value!r} cannot move to "
                f"{target.value!r}. It may move one step, forwards or back."
            )
        updated = await self.bills.set_status(
            bill_id, target, actor=actor, moment=datetime.now(UTC)
        )
        if updated is None:
            self.logger.error(
                "Bill %s vanished while %s was moving it.", bill_id, actor
            )
            raise MTBillNotFound(f"No bill {bill_id!r}.")
        self.logger.info("%s moved bill %s to %s.", actor, updated.number, target.value)
        return updated

    async def document(self, bill_id: str) -> Tuple[bytes, str]:
        """Return an invoice's document and the filename it downloads as.

        Args:
            bill_id (str): The invoice to read.

        Returns:
            Tuple[bytes, str]: The PDF, and the filename.

        Raises:
            MTBillNotFound: If no such invoice exists.
            MTBillDocumentUnavailable: If the document cannot be read.
            MTBillDocumentStorageUnavailable: If no object store is configured.

        Notes:
            **The filename is derived from the invoice number**, never from
            anything a client sends. A filename taken from a request is how a
            download endpoint starts writing files somebody else chose the name
            of.
        """
        bill = await self.get(bill_id)
        documents = self._require_documents()
        if not bill.document_key:
            self.logger.error(
                "Bill %s has no stored document to download.", bill.number
            )
            raise MTBillDocumentUnavailable(
                f"Invoice {bill.number} has no stored document."
            )
        payload = await documents.fetch_invoice(bill.document_key)
        if payload is None:
            self.logger.error(
                "The document of bill %s could not be read from %s.",
                bill.number,
                bill.document_key,
            )
            raise MTBillDocumentUnavailable(
                f"The document of invoice {bill.number} is unavailable."
            )
        self.logger.info("Serving %d bytes of invoice %s.", len(payload), bill.number)  # noqa: E501
        return payload, f"{bill.number}.pdf"

    async def mark_sent(self, bill_id: str, sent_at: datetime) -> Bill:
        """Record that an invoice reached its customer.

        Args:
            bill_id (str): The invoice that was emailed.
            sent_at (datetime): When it went out.

        Returns:
            Bill: The updated invoice.

        Raises:
            MTBillNotFound: If no such invoice exists.
        """
        updated = await self.bills.mark_sent(bill_id, sent_at)
        if updated is None:
            self.logger.error(
                "Cannot record a dispatch: no bill found with id %s.", bill_id
            )
            raise MTBillNotFound(f"No bill {bill_id!r}.")
        self.logger.info("Invoice %s reached its customer.", updated.number)
        return updated

    async def get_run(self, run_id: str) -> BillingRun:
        """Return one generation run.

        Args:
            run_id (str): The run to read.

        Returns:
            BillingRun: The run.

        Raises:
            MTBillingRunNotFound: If no such run exists.
        """
        run = await self.runs.get(run_id)
        if run is None:
            self.logger.warning("No billing run found with id %s.", run_id)
            raise MTBillingRunNotFound(f"No billing run {run_id!r}.")
        return run

    async def list_runs(
        self, company_id: str, page: int = 1, size: Optional[int] = None
    ) -> List[BillingRun]:
        """Return a page of an agency's generation runs.

        Args:
            company_id (str): The agency whose runs are being read.
            page (int): One-based page number.
            size (Optional[int]): Page size.

        Returns:
            List[BillingRun]: The runs, most recently requested first.
        """
        self.logger.debug("Listing the billing runs of agency %s.", company_id)
        return await self.runs.list(page=page, size=size, company_id=company_id)  # noqa: E501

    async def bill_one(
        self,
        company_id: str,
        customer_id: str,
        reference_date: date,
        actor: str,
        language: Language = Language.FR,
    ) -> Bill:
        """Bill a single customer for the period containing a day.

        Args:
            company_id (str): The agency issuing it.
            customer_id (str): The customer being billed.
            reference_date (date): Any day inside the period.
            actor (str): The account asking for it.
            language (Language): The language to write the document in.

        Returns:
            Bill: The issued invoice.

        Raises:
            MTBillAlreadyIssued: If the period is billed already.
            MTBillNothingToBill: If the customer owes nothing for it.

        Notes:
            The one path where an empty period and an already-billed one are
            **errors** rather than customers to pass over. A run over everybody
            skips both silently, because most customers have no work in most
            weeks; a caller who named one customer asked a question and is owed
            an answer.
        """
        period_start, period_end = await self.window_for(reference_date)
        if await self.bills.exists_for_period(customer_id, period_start, period_end):  # noqa: E501
            self.logger.warning(
                "%s asked to bill customer %s for %s..%s, which is billed already.",
                actor,
                customer_id,
                period_start,
                period_end,
            )
            raise MTBillAlreadyIssued(
                f"Customer {customer_id!r} is already billed for "
                f"{period_start}..{period_end}."
            )
        issued = await self.generate_for_customer(
            company_id=company_id,
            customer_id=customer_id,
            period_start=period_start,
            period_end=period_end,
            generated_by=actor,
            language=language,
        )
        if issued is None:
            self.logger.warning(
                "Customer %s has nothing to bill for %s..%s.",
                customer_id,
                period_start,
                period_end,
            )
            raise MTBillNothingToBill(
                f"Customer {customer_id!r} owes nothing for "
                f"{period_start}..{period_end}."
            )
        return issued
