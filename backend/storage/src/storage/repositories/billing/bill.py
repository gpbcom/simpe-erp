from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from hashlib import blake2b
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third-party imports
from sqlalchemy import Select, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.billing.bill import Bill
from models.enums import BillStatus
from models.schemas.requests.billing.bill_filter import BillFilter
from storage.mappers.billing.bill_mapper import BillMapper
from storage.orm.billing.bill_row import BillRow
from storage.repositories.base import BaseRepository


class BillRepository(BaseRepository[BillRow]):
    """Reads and writes invoices, and allocates their legal numbering.

    Attributes:
        NUMBER_TEMPLATE (str): How an invoice number is composed.
        mapper (BillMapper): Converts between the row and the model.

    Notes:
        - **Three things guard against billing a customer twice**, and only the
          second of them actually guarantees it: :meth:`find_overlapping` is
          the friendly check a run makes first so a re-run is a reported no-op;
          the unique index on ``(customer_id, period_start, period_end)`` is
          what stops two runs racing past that check; and
          :meth:`next_number` serialises the numbering so the loser of such a
          race fails rather than leaving a gap.
        - There is no ``delete``. A number withdrawn from the series is exactly
          the gap French invoicing forbids, so a mistaken invoice is corrected
          by a credit note — a document of its own, and out of scope here.
        - The narrow writers (:meth:`attach_document`, :meth:`set_status`,
          :meth:`mark_sent`) exist for the reason
          :meth:`~storage.repositories.quoting.quote.QuoteRepository.set_status`
          does: recording that an invoice was emailed must not be able to change
          what it charges.
    """

    NUMBER_TEMPLATE: str = "FA-{year}-{sequence:06d}"

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        super().__init__(session=session, row_class=BillRow)
        self.mapper = BillMapper()

    ############################
    # Internal Helpers Methods #
    ############################

    async def _lock_company(self, company_id: str) -> None:
        """Hold an agency's invoice series against a concurrent allocation.

        Args:
            company_id (str): The agency to lock.

        Notes:
            - Transaction-scoped, so nothing has to remember to release it —
              including a worker killed mid-run. The same advisory-lock pattern
              the intervention repository uses around its own destructive write.
            - **The lock is an optimisation, not the guarantee.** It is
              PostgreSQL-only and silently skipped elsewhere, and the test schema
              runs on SQLite; what actually keeps the series unique is the index
              on ``(company_id, sequence_year, sequence)``. What the lock buys is
              that two concurrent runs queue rather than collide, so neither has
              to be retried and neither leaves a burnt number behind.
        """
        dialect = self.session.get_bind().dialect.name
        if dialect != "postgresql":
            self.logger.debug(
                "Not locking the series of agency %s: %s has no advisory locks.",
                company_id,
                dialect,
            )
            return
        digest = blake2b(f"bills:{company_id}".encode("utf-8"), digest_size=8).digest()  # noqa: E501
        key = int.from_bytes(digest, byteorder="big", signed=True)
        self.logger.debug(
            "Locking the invoice series of agency %s (key %d).",
            company_id,
            key,  # noqa: E501
        )
        try:
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": key}
            )
        except SQLAlchemyError as exc:
            self.logger.error(
                "Could not lock the invoice series of agency %s: %s. The "
                "allocation proceeds unserialised and may collide.",
                company_id,
                exc,
            )

    def _build_query(
        self,
        company_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        bill_filter: Optional[BillFilter] = None,
    ) -> Select:
        """Build the filtered select shared by ``list`` and ``count``.

        Args:
            company_id (Optional[str]): Restrict to one agency's invoices.
            customer_id (Optional[str]): Restrict to one customer's invoices.
            bill_filter (Optional[BillFilter]): The richer filter from the
                screen.

        Returns:
            Select: The filtered statement, without ordering or pagination.

        Notes:
            The caller's own scoping is applied first and unconditionally, and
            the screen's filter is never allowed to widen it. An invoice list is
            the one screen where a filter that could escape its agency would
            show one customer's money to another's manager.
        """
        applied = bill_filter or BillFilter()
        self.logger.debug(
            "Building the bill query from %s.",
            applied.model_dump(exclude_none=True),
        )
        if applied.is_empty() and not any((company_id, customer_id)):
            self.logger.info("No filter was given; the query is every bill.")

        statement = select(BillRow)
        if company_id is not None:
            statement = statement.where(BillRow.company_id == company_id)
        if customer_id is not None:
            statement = statement.where(BillRow.customer_id == customer_id)

        if applied.customer_id and customer_id is None:
            statement = statement.where(BillRow.customer_id == applied.customer_id)  # noqa: E501
        elif applied.customer_id and applied.customer_id != customer_id:
            self.logger.warning(
                "A bill filter asked for customer %r while the caller is "
                "scoped to %r; the scope wins.",
                applied.customer_id,
                customer_id,
            )
        if applied.status is not None:
            statement = statement.where(BillRow.status == applied.status.value)
        for fragment in (applied.search, applied.number):
            if fragment:
                statement = statement.where(
                    BillRow.number.ilike(f"%{fragment.strip().lower()}%")
                )
        if applied.is_sent is not None:
            statement = statement.where(
                BillRow.sent_at.isnot(None)
                if applied.is_sent
                else BillRow.sent_at.is_(None)
            )
        if applied.period_start is not None:
            statement = statement.where(BillRow.period_start >= applied.period_start)  # noqa: E501
        if applied.period_end is not None:
            statement = statement.where(BillRow.period_end <= applied.period_end)  # noqa: E501
        return statement

    ############################
    # Publicly Exposed Methods #
    ############################

    async def next_number(self, company_id: str, year: int) -> Tuple[int, str]:
        """Allocate the next position in an agency's invoice series.

        Args:
            company_id (str): The agency issuing the invoice.
            year (int): The year the series belongs to.

        Returns:
            Tuple[int, str]: The position and the number composed from it.

        Notes:
            - French invoicing requires an unbroken, chronological sequence per
              issuer. The position is therefore ``MAX + 1`` over the agency's own
              rows for the year, taken under a transaction-scoped advisory lock,
              rather than anything derived from a timestamp or a row count —
              both of which produce duplicates the moment two runs overlap.
            - The series restarts at one each January, which is what the year in
              the number is for.
        """
        await self._lock_company(company_id)
        statement = select(func.max(BillRow.sequence)).where(
            BillRow.company_id == company_id,
            BillRow.sequence_year == year,
        )
        result = await self.session.execute(statement)
        highest = result.scalar_one_or_none()
        sequence = (highest or 0) + 1
        number = self.NUMBER_TEMPLATE.format(year=year, sequence=sequence)
        self.logger.info(
            "Allocated invoice number %s to agency %s (position %d of %d).",
            number,
            company_id,
            sequence,
            year,
        )
        return sequence, number

    async def find_overlapping(
        self, customer_id: str, period_start: date, period_end: date
    ) -> List[Bill]:
        """Return the invoices whose period intersects a window.

        Args:
            customer_id (str): The customer being considered.
            period_start (date): First day of the window, inclusive.
            period_end (date): Last day of the window, inclusive.

        Returns:
            List[Bill]: The overlapping invoices, earliest period first. Empty
            when the window is free.

        Notes:
            - **Wider than the exact-window match this replaced.** Comparing
              the two dates catches a re-run; it does not catch a customer whose
              granularity changed. Billed for the week of 1–7 July and then
              moved to monthly, their July invoice would cover that week a
              second time — same customer, same days, two documents, and the
              unique index sees nothing because the windows differ.
            - Written as "starts before the other ends, and ends after the
              other starts", which is the only overlap test that needs no cases:
              containment, partial overlap in either direction and an exact
              match are all the same expression.
        """
        statement = (
            select(BillRow)
            .where(
                BillRow.customer_id == customer_id,
                BillRow.period_start <= period_end,
                BillRow.period_end >= period_start,
            )
            .order_by(BillRow.period_start)
        )
        result = await self.session.execute(statement)
        rows = list(result.scalars().unique().all())
        if rows:
            self.logger.warning(
                "Customer %s already has %d invoice(s) covering part of %s..%s: %s.",
                customer_id,
                len(rows),
                period_start,
                period_end,
                ", ".join(row.number for row in rows),
            )
        self.logger.debug(
            "%d invoice(s) of customer %s overlap %s..%s.",
            len(rows),
            customer_id,
            period_start,
            period_end,
        )
        return [self.mapper.to_model(row) for row in rows]

    async def create(self, bill: Bill) -> Bill:
        """Store a new invoice and its charges.

        Args:
            bill (Bill): The invoice to store.

        Returns:
            Bill: The stored invoice, carrying its identifier.

        Raises:
            IntegrityError: If the customer is already billed for the period, or
                the number or series position is taken.
        """
        self.logger.info(
            "Creating bill %s for customer %s (%s..%s, %s TTC).",
            bill.number,
            bill.customer_id,
            bill.period_start,
            bill.period_end,
            bill.total_ttc,
        )
        row = self.mapper.to_row(bill)
        self.session.add(row)
        await self.session.flush()
        self.logger.debug("Stored bill row %s.", row.id)
        return self.mapper.to_model(row)

    async def get(self, bill_id: str) -> Optional[Bill]:
        """Return one invoice.

        Args:
            bill_id (str): The invoice to read.

        Returns:
            Optional[Bill]: The invoice, or ``None`` when there is no such row.
        """
        self.logger.debug("Fetching bill %s.", bill_id)
        row = await self._get_row(bill_id)
        if row is None:
            self.logger.warning("No bill found with id %s.", bill_id)
            return None
        return self.mapper.to_model(row)

    async def get_by_number(self, number: str) -> Optional[Bill]:
        """Return one invoice by its human-facing number.

        Args:
            number (str): The invoice number, as printed.

        Returns:
            Optional[Bill]: The invoice, or ``None`` when there is no such row.

        Notes:
            The number is upper-cased on the way in, matching the model's own
            normalisation, so a customer quoting it in lower case over the
            telephone still finds their invoice.
        """
        self.logger.debug("Fetching bill numbered %s.", number)
        statement = select(BillRow).where(BillRow.number == number.strip().upper())  # noqa: E501
        row = await self._fetch_one(statement)
        if row is None:
            self.logger.warning("No bill found numbered %s.", number)
            return None
        return self.mapper.to_model(row)

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        company_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        bill_filter: Optional[BillFilter] = None,
    ) -> List[Bill]:
        """Return a page of invoices, newest first.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            company_id (Optional[str]): Restrict to one agency's invoices.
            customer_id (Optional[str]): Restrict to one customer's invoices.
            bill_filter (Optional[BillFilter]): The richer filter from the
                screen.

        Returns:
            List[Bill]: The matching invoices.

        Notes:
            Ordered by the period billed and then by the number, so a customer's
            invoices read as a run of months and two invoices for one month —
            which the unique index makes impossible — could not appear in a
            different order between two reads.
        """
        statement = self._build_query(company_id, customer_id, bill_filter)
        statement = statement.order_by(
            BillRow.period_start.desc(), BillRow.number.desc()
        )
        rows = await self._fetch_all(self._paginate(statement, page, size))
        self.logger.info("Loaded %d bill(s).", len(rows))
        return self.mapper.to_models(rows)

    async def count(
        self,
        company_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        bill_filter: Optional[BillFilter] = None,
    ) -> int:
        """Return how many invoices match a filter.

        Args:
            company_id (Optional[str]): Restrict to one agency's invoices.
            customer_id (Optional[str]): Restrict to one customer's invoices.
            bill_filter (Optional[BillFilter]): The richer filter from the
                screen.

        Returns:
            int: The number of matching invoices.
        """
        total = await self._count(
            self._build_query(company_id, customer_id, bill_filter)
        )
        self.logger.debug("Counted %d bill(s).", total)
        return total

    async def list_for_run(self, run_id: str) -> List[Bill]:
        """Return every invoice a generation run wrote.

        Args:
            run_id (str): The run to read.

        Returns:
            List[Bill]: The invoices the run produced, oldest number first.

        Notes:
            Unpaginated by design, like the planner's own workload query: a run
            is reported on whole, and paging through it would show a manager a
            month they have to scroll to finish reading.
        """
        self.logger.debug("Loading the bills written by run %s.", run_id)
        statement = (
            select(BillRow)
            .where(BillRow.billing_run_id == run_id)
            .order_by(BillRow.number)
        )
        rows = await self._fetch_all(statement)
        if not rows:
            self.logger.warning("Run %s wrote no bill.", run_id)
        self.logger.info("Run %s wrote %d bill(s).", run_id, len(rows))
        return self.mapper.to_models(rows)

    async def attach_document(self, bill_id: str, document_key: str) -> Optional[Bill]:  # noqa: E501
        """Record where an invoice's rendered document is stored.

        Args:
            bill_id (str): The invoice to update.
            document_key (str): The object key the document was written under.

        Returns:
            Optional[Bill]: The updated invoice, or ``None`` when there is no
            such row.

        Notes:
            A narrow writer rather than a whole update, so attaching a document
            cannot change what the invoice charges. The key is stored and never
            a URL: these objects are private and are only ever read back
            server-side.
        """
        row = await self._get_row(bill_id)
        if row is None:
            self.logger.warning(
                "Cannot attach a document: no bill found with id %s.", bill_id
            )
            return None
        self.logger.info("Attaching document %s to bill %s.", document_key, row.number)  # noqa: E501
        row.document_key = document_key
        await self.session.flush()
        return self.mapper.to_model(row)

    async def set_status(
        self,
        bill_id: str,
        status: BillStatus,
        actor: Optional[str] = None,
        moment: Optional[datetime] = None,
    ) -> Optional[Bill]:
        """Move an invoice to a new commercial status.

        Args:
            bill_id (str): The invoice to update.
            status (BillStatus): The status to move it to.
            actor (Optional[str]): The account making the change.
            moment (Optional[datetime]): When the change was made.

        Returns:
            Optional[Bill]: The updated invoice, or ``None`` when there is no
            such row.

        Notes:
            - Whether the move is *allowed* is the service's decision, taken
              against :meth:`~models.enums.BillStatus.can_move_to`. This
              repository writes what it is told, because a repository that also
              enforced the lifecycle would be a second place the rule lived.
            - Reaching :attr:`~models.enums.BillStatus.ACCEPTED` stamps who
              approved it and when — the answer to "who agreed to send this?",
              which the record could not otherwise give. Reaching
              :attr:`~models.enums.BillStatus.PAID` stamps the settlement day.
              Stepping back clears neither: an invoice that was approved and
              then un-approved was still approved once, and erasing that would
              be rewriting the audit trail rather than correcting a status.
        """
        row = await self._get_row(bill_id)
        if row is None:
            self.logger.warning(
                "Cannot set a status: no bill found with id %s.", bill_id
            )
            return None
        self.logger.info(
            "Moving bill %s from %s to %s (by %s).",
            row.number,
            row.status,
            status.value,
            actor,
        )
        row.status = status.value
        if status is BillStatus.ACCEPTED and row.validated_at is None:
            row.validated_by = actor
            row.validated_at = moment
        if status is BillStatus.PAID and row.paid_on is None:
            row.paid_on = moment.date() if moment else None
        await self.session.flush()
        return self.mapper.to_model(row)

    async def mark_sent(self, bill_id: str, sent_at: datetime) -> Optional[Bill]:  # noqa: E501
        """Record that an invoice reached its customer.

        Args:
            bill_id (str): The invoice to update.
            sent_at (datetime): When it was emailed.

        Returns:
            Optional[Bill]: The updated invoice, or ``None`` when there is no
            such row.

        Notes:
            Only the timestamp. Advancing the status is the caller's separate
            act, so an invoice whose delivery succeeded but whose status write
            failed still records that the customer has it — which is the fact
            that matters if they telephone about it.
        """
        row = await self._get_row(bill_id)
        if row is None:
            self.logger.warning(
                "Cannot mark as sent: no bill found with id %s.", bill_id
            )
            return None
        self.logger.info("Bill %s was emailed at %s.", row.number, sent_at)
        row.sent_at = sent_at
        await self.session.flush()
        return self.mapper.to_model(row)
