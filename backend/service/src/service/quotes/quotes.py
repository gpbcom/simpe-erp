from __future__ import annotations

# Standard library imports
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from logging import Logger, getLogger
from typing import ClassVar, Dict, FrozenSet, List, Optional, Tuple

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.configuration.pricing_config import PricingConfig
from models.enums import QuoteStatus, ServiceCategory
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from models.quoting.quote_type_week_aggregate import QuoteTypeWeekAggregate
from service.quotes.exceptions import (
    MTPricingUnknownInterventionType,
    MTQuoteForbidden,
    MTQuoteNotEditable,
    MTQuoteNotFound,
    MTQuoteNotPriced,
)
from storage.repositories.intervention_type import InterventionTypeRepository
from storage.repositories.quote import QuoteRepository


class QuoteService:
    """Composes, prices and progresses quotes.

    Attributes:
        EDITABLE_STATUSES (ClassVar[FrozenSet[QuoteStatus]]): The statuses in
            which a quote's lines may still change.
        quotes (QuoteRepository): The quote store.
        types (InterventionTypeRepository): The catalog store.
        CENTS (ClassVar[Decimal]): The quantum every amount is rounded to.
        config (PricingConfig): The agency-wide pricing rules.
        logger (Logger): Logger for quote operations.

    Notes:
        - A quote's lines are editable only while it is a draft. Once it has been
          sent, what the customer is looking at must be what the system holds —
          editing underneath them is how a customer accepts one thing and gets
          billed for another.
        - Pricing is re-run whenever the lines change, and never on read. The
          stored amounts are the offer; recomputing them at display time would
          silently reprice an issued quote after its type is repriced.
    """

    EDITABLE_STATUSES: ClassVar[FrozenSet[QuoteStatus]] = frozenset({QuoteStatus.DRAFT})  # noqa: E501
    # A quote reaches the customer from a draft. It cannot be sent while a
    # manager still owes it a decision, and re-sending one already sent, or one
    # the customer has answered, would overwrite the answer with the offer.
    SENDABLE_STATUSES: ClassVar[FrozenSet[QuoteStatus]] = frozenset({QuoteStatus.DRAFT})

    CENTS: ClassVar[Decimal] = Decimal("0.01")

    def __init__(
        self,
        quotes: QuoteRepository,
        types: InterventionTypeRepository,
        config: PricingConfig,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            quotes (QuoteRepository): The quote store.
            types (InterventionTypeRepository): The catalog store.
            CENTS (ClassVar[Decimal]): The quantum every amount is rounded to.
        config (PricingConfig): The agency-wide pricing rules.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.quotes = quotes
        self.types = types
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("QuoteService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _price(self, quote: Quote) -> Quote:
        """Price a quote against the catalog entries its lines name.

        Args:
            quote (Quote): The quote to price.

        Returns:
            Quote: A priced copy.

        Raises:
            MTPricingUnknownInterventionType: If a line names a missing type.

        Notes:
            The types are fetched in one query rather than one per line, so a
            twenty-line quote costs one round trip.
        """
        type_ids = [line.intervention_type_id for line in quote.lines]
        intervention_types: Dict[str, InterventionType] = await self.types.get_many(
            type_ids
        )
        return self.price_quote(quote, intervention_types)

    async def _move_to(self, quote_id: str, status: QuoteStatus) -> Quote:
        """Move a quote to a status.

        Args:
            quote_id (str): The quote to move.
            status (QuoteStatus): The status to move it to.

        Returns:
            Quote: The updated quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
        """
        updated = await self.quotes.set_status(quote_id, status)
        if updated is None:
            self.logger.warning(
                "Status change requested for absent quote %s.", quote_id
            )
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        return updated

    def _utc_now(self) -> datetime:
        """Return the current instant as timezone-aware UTC.

        Returns:
            datetime: The current instant in UTC.

        Notes:
            Read here rather than in the model, which keeps the quote free of
            ambient state and lets a test pin the clock by patching one method.
        """
        return datetime.now(UTC)

    def _to_cents(self, amount: Decimal) -> Decimal:
        """Round an exact amount to whole cents.

        Args:
            amount (Decimal): The exact amount.

        Returns:
            Decimal: The amount rounded to two decimals, half away from zero.

        Notes:
            ``ROUND_HALF_UP`` is the invoicing convention. Python's default is
            ``ROUND_HALF_EVEN``, which would send 95.715 down to 95.71 — a cent
            the customer would have to be told about.
        """
        return amount.quantize(self.CENTS, rounding=ROUND_HALF_UP)

    def _monday_of(self, iso_year: int, iso_week: int) -> date:
        """Return the Monday that starts an ISO week.

        Args:
            iso_year (int): The ISO year.
            iso_week (int): The ISO week number.

        Returns:
            date: The Monday of that week.

        Notes:
            Computed from 4 January, which ISO 8601 guarantees falls in week 1
            of its own year. Anchoring on 1 January instead would be wrong for
            every year that starts on a Friday, Saturday or Sunday, where the
            1st belongs to the last week of the previous year.
        """
        fourth_of_january = date(iso_year, 1, 4)
        week_one_monday = fourth_of_january - timedelta(
            days=fourth_of_january.isoweekday() - 1
        )
        return week_one_monday + timedelta(weeks=iso_week - 1)

    def _build(
        self,
        key: Tuple[str, int, int],
        bucket: List[QuoteLine],
        intervention_types: Dict[str, InterventionType],
    ) -> QuoteTypeWeekAggregate:
        """Build one aggregate from the lines that fell in its bucket.

        Args:
            key (Tuple[str, int, int]): The type identifier, ISO year and ISO
                week the bucket represents.
            bucket (List[QuoteLine]): The lines in that bucket.
            intervention_types (Dict[str, InterventionType]): The types behind
                the lines, keyed by identifier.

        Returns:
            QuoteTypeWeekAggregate: The totals for that type and week.

        Raises:
            KeyError: If the type is absent from the mapping.
        """
        type_id, iso_year, iso_week = key
        intervention_type = intervention_types[type_id]
        return QuoteTypeWeekAggregate(
            intervention_type_id=type_id,
            intervention_type_name=intervention_type.name,
            iso_year=iso_year,
            iso_week=iso_week,
            week_start_date=self._monday_of(iso_year, iso_week),
            line_count=len(bucket),
            total_minutes=sum(line.duration_minutes for line in bucket),
            total_ht=sum((line.total_ht for line in bucket), Decimal("0.00")),
            vat_amount=sum((line.vat_amount for line in bucket), Decimal("0.00")),
            total_ttc=sum((line.total_ttc for line in bucket), Decimal("0.00")),
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, quote: Quote, author_id: Optional[str] = None) -> Quote:
        """Create a quote and price whatever lines it arrives with.

        Args:
            quote (Quote): The quote to create.
            author_id (Optional[str]): The account writing it, recorded as the
                author. ``None`` leaves whatever the payload carried.

        Returns:
            Quote: The stored, priced quote.

        Raises:
            MTPricingUnknownInterventionType: If a line names a missing type.

        Notes:
            The author is taken from the caller's own account, never from the
            payload. A quote naming somebody else as its author would land in
            their list, and they would be the one a manager asks about a price
            they never set.
        """
        self.logger.info(
            "Creating quote %s for customer %s, authored by %s.",
            quote.reference,
            quote.customer_id,
            author_id,
        )
        priced = await self._price(quote)
        if author_id is not None:
            priced = priced.model_copy(update={"authored_by": author_id})
        return await self.quotes.create(priced)

    async def get(self, quote_id: str) -> Quote:
        """Return a quote by identifier.

        Args:
            quote_id (str): The identifier to look up.

        Returns:
            Quote: The quote, with its lines and weekly totals.

        Raises:
            MTQuoteNotFound: If no such quote exists.
        """
        found = await self.quotes.get(quote_id)
        if found is None:
            self.logger.warning("Quote %s does not exist.", quote_id)
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        return found

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        customer_id: Optional[str] = None,
        status: Optional[QuoteStatus] = None,
        authored_by: Optional[str] = None,
    ) -> List[Quote]:
        """Return a page of quotes.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            customer_id (Optional[str]): Restrict to one customer.
            status (Optional[QuoteStatus]): Restrict to one status.
            authored_by (Optional[str]): Restrict to one author's quotes.

        Returns:
            List[Quote]: The matching quotes.
        """
        return await self.quotes.list(
            page=page,
            size=size,
            customer_id=customer_id,
            status=status,
            authored_by=authored_by,
        )

    async def replace_lines(self, quote_id: str, quote: Quote) -> Quote:
        """Replace a draft quote's lines and reprice it.

        Args:
            quote_id (str): The quote to change.
            quote (Quote): A quote carrying the new lines.

        Returns:
            Quote: The stored, repriced quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteNotEditable: If the quote is past draft.
            MTPricingUnknownInterventionType: If a line names a missing type.

        Notes:
            Only the lines are taken from the payload. The reference, the
            customer and the status stay as stored, so editing lines cannot
            reassign a quote to another customer or quietly accept it.
        """
        existing = await self.get(quote_id)
        if existing.status not in self.EDITABLE_STATUSES:
            self.logger.warning(
                "Refused to edit quote %s: it is %s, not a draft.",
                existing.reference,
                existing.status.value,
            )
            raise MTQuoteNotEditable(
                f"Quote {existing.reference!r} is {existing.status.value} and "
                f"can no longer be edited. Only a draft may change."
            )
        self.logger.info(
            "Replacing the %d line(s) of quote %s with %d new one(s).",
            len(existing.lines),
            existing.reference,
            len(quote.lines),
        )
        priced = await self._price(existing.model_copy(update={"lines": quote.lines}))
        updated = await self.quotes.update(priced)
        if updated is None:
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        return updated

    async def reprice(self, quote_id: str) -> Quote:
        """Recompute a draft quote's amounts against the current catalog.

        Args:
            quote_id (str): The quote to reprice.

        Returns:
            Quote: The stored, repriced quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteNotEditable: If the quote is past draft.

        Notes:
            Restricted to drafts for the same reason editing is: an issued
            quote must keep the figures the customer was shown, even after the
            catalog moves under it.
        """
        existing = await self.get(quote_id)
        if existing.status not in self.EDITABLE_STATUSES:
            raise MTQuoteNotEditable(
                f"Quote {existing.reference!r} is {existing.status.value} and "
                f"cannot be repriced. Its figures are what the customer saw."
            )
        self.logger.info("Repricing quote %s.", existing.reference)
        updated = await self.quotes.update(await self._price(existing))
        if updated is None:
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        return updated

    async def send(self, quote_id: str) -> Quote:
        """Move a priced draft to sent.

        Args:
            quote_id (str): The quote to send.

        Returns:
            Quote: The updated quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteNotPriced: If the quote has no priced lines.

        Notes:
            An unpriced or empty quote cannot be sent. Both would reach the
            customer as an offer of nothing for nothing.
        """
        existing = await self.get(quote_id)
        if not existing.is_priced():
            self.logger.warning(
                "Refused to send quote %s: it has no priced lines.",
                existing.reference,
            )
            raise MTQuoteNotPriced(
                f"Quote {existing.reference!r} has no priced lines and cannot be sent."
            )
        if existing.status not in self.SENDABLE_STATUSES:
            self.logger.warning(
                "Refused to send quote %s: it is %s.",
                existing.reference,
                existing.status.value,
            )
            raise MTQuoteNotEditable(
                f"Quote {existing.reference!r} is {existing.status.value} and "
                f"cannot be sent."
            )
        return await self._move_to(quote_id, QuoteStatus.SENT)

    async def submit_for_validation(self, quote_id: str, author_id: str) -> Quote:
        """Put an assistant's draft in front of a manager.

        Args:
            quote_id (str): The quote to submit.
            author_id (str): The account submitting it.

        Returns:
            Quote: The submitted quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteNotPriced: If the quote has no priced lines.
            MTQuoteNotEditable: If the quote is not a draft.
            MTQuoteForbidden: If the caller did not write it.

        Notes:
            **The authorship check is here, not in the endpoint.** A route guard
            proves the caller is an assistant; it cannot stop assistant A
            submitting assistant B's draft, and only a comparison against the
            stored author can. A manager is allowed through: they own every
            quote in the agency, and refusing them their own draft would be
            gratuitous.
        """
        existing = await self.get(quote_id)
        if existing.authored_by is not None and existing.authored_by != author_id:
            self.logger.warning(
                "Account %s tried to submit quote %s, written by %s.",
                author_id,
                existing.reference,
                existing.authored_by,
            )
            raise MTQuoteForbidden("You may only submit a quote you wrote.")
        if not existing.status.is_editable():
            self.logger.warning(
                "Refused to submit quote %s: it is %s, not a draft.",
                existing.reference,
                existing.status.value,
            )
            raise MTQuoteNotEditable(
                f"Quote {existing.reference!r} is {existing.status.value} and "
                f"cannot be submitted for validation."
            )
        if not existing.is_priced():
            self.logger.warning(
                "Refused to submit quote %s: it has no priced lines.",
                existing.reference,
            )
            raise MTQuoteNotPriced(
                f"Quote {existing.reference!r} has no priced lines and cannot "
                f"be submitted for validation."
            )
        submitted = await self.quotes.record_submission(quote_id, self._utc_now())
        if submitted is None:
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        self.logger.info(
            "Quote %s is awaiting validation, submitted by %s.",
            submitted.reference,
            author_id,
        )
        return submitted

    async def validate(self, quote_id: str, validator_id: str) -> Quote:
        """Approve a submitted quote, making it sendable.

        Args:
            quote_id (str): The quote to validate.
            validator_id (str): The manager ruling on it.

        Returns:
            Quote: The validated quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteNotEditable: If the quote is not awaiting validation.
            MTQuoteNotPriced: If the quote has no priced lines.

        Notes:
            Validation moves the quote to ``SENT``: the manager's approval *is*
            the act of issuing the offer, and there is no second button to
            press. Sending it back to ``DRAFT`` instead was the obvious
            alternative and is wrong — an approved quote would then be
            indistinguishable from one nobody had looked at, and the assistant
            could edit the figures a manager had just signed off.
        """
        existing = await self.get(quote_id)
        if not existing.status.is_awaiting_validation():
            self.logger.warning(
                "Refused to validate quote %s: it is %s.",
                existing.reference,
                existing.status.value,
            )
            raise MTQuoteNotEditable(
                f"Quote {existing.reference!r} is {existing.status.value} and "
                f"is not awaiting validation."
            )
        if not existing.is_priced():
            raise MTQuoteNotPriced(
                f"Quote {existing.reference!r} has no priced lines and cannot "
                f"be validated."
            )
        validated = await self.quotes.record_validation(
            quote_id,
            status=QuoteStatus.SENT,
            validated_by=validator_id,
            validated_at=self._utc_now(),
        )
        if validated is None:
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        self.logger.info(
            "Quote %s validated by %s; it may now be sent.",
            validated.reference,
            validator_id,
        )
        return validated

    async def refuse_validation(self, quote_id: str, validator_id: str) -> Quote:
        """Send a submitted quote back to its author.

        Args:
            quote_id (str): The quote to send back.
            validator_id (str): The manager ruling on it.

        Returns:
            Quote: The quote, back in draft.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteNotEditable: If the quote is not awaiting validation.

        Notes:
            Refusal returns the quote to ``DRAFT`` rather than to ``REJECTED``.
            ``REJECTED`` means *the customer said no*, and collapsing the two
            would lose the difference between an offer the agency declined to
            make and one the family turned down — which are opposite facts about
            the same customer. Back in draft, the assistant can fix the figures
            and submit again.
        """
        existing = await self.get(quote_id)
        if not existing.status.is_awaiting_validation():
            self.logger.warning(
                "Refused to rule on quote %s: it is %s.",
                existing.reference,
                existing.status.value,
            )
            raise MTQuoteNotEditable(
                f"Quote {existing.reference!r} is {existing.status.value} and "
                f"is not awaiting validation."
            )
        returned = await self.quotes.record_validation(
            quote_id,
            status=QuoteStatus.DRAFT,
            validated_by=validator_id,
            validated_at=self._utc_now(),
        )
        if returned is None:
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        self.logger.warning(
            "Quote %s was sent back to its author by %s.",
            returned.reference,
            validator_id,
        )
        return returned

    async def accept(self, quote_id: str) -> Quote:
        """Record a customer's acceptance.

        Args:
            quote_id (str): The quote to accept.

        Returns:
            Quote: The updated quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteNotPriced: If the quote has no priced lines.

        Notes:
            Acceptance is what makes a quote's lines schedulable, so this is
            the moment work is committed to. The priced check is repeated here
            rather than assumed from :meth:`send`, because a quote can reach
            acceptance without passing through this service.
        """
        existing = await self.get(quote_id)
        if not existing.is_priced():
            raise MTQuoteNotPriced(
                f"Quote {existing.reference!r} has no priced lines and cannot "
                f"be accepted."
            )
        self.logger.info(
            "Quote %s accepted: %d line(s) are now schedulable.",
            existing.reference,
            len(existing.lines),
        )
        return await self._move_to(quote_id, QuoteStatus.ACCEPTED)

    async def reject(self, quote_id: str) -> Quote:
        """Record a customer's refusal.

        Args:
            quote_id (str): The quote to reject.

        Returns:
            Quote: The updated quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
        """
        return await self._move_to(quote_id, QuoteStatus.REJECTED)

    def base_rate_for(self, intervention_type: InterventionType) -> Decimal:
        """Return the hourly rate a type bills at, before any surcharge.

        Args:
            intervention_type (InterventionType): The type being billed.

        Returns:
            Decimal: The type's own rate, or the agency default.
        """
        resolved = intervention_type.effective_hourly_rate_ht(
            self.config.base_hourly_rate_ht
        )
        if intervention_type.base_hourly_rate_ht is None:
            self.logger.debug(
                "Type %s bills the agency default of %s.",
                intervention_type.code,
                resolved,
            )
        else:
            self.logger.debug(
                "Type %s bills its own rate of %s.", intervention_type.code, resolved
            )
        return resolved

    def multiplier_for(self, service_date: date) -> Decimal:
        """Return the multiplier applying to a service date.

        Args:
            service_date (date): The day the service is delivered.

        Returns:
            Decimal: ``1`` on an ordinary day, ``1.25`` on a surcharged
            Sunday, ``1.50`` on Christmas Day or New Year's Day.
        """
        multiplier = self.config.multiplier_for(service_date)
        if multiplier != Decimal("1"):
            self.logger.info(
                "%s carries a surcharge: billing at x%s.", service_date, multiplier
            )
        else:
            self.logger.debug("%s carries no surcharge.", service_date)
        return multiplier

    def vat_rate_for(self, intervention_type: InterventionType) -> Decimal:
        """Return the VAT rate a type is taxed at.

        Args:
            intervention_type (InterventionType): The type being billed.

        Returns:
            Decimal: ``0.055`` for a necessity service, ``0.20`` for a comfort
            one.
        """
        rate = intervention_type.vat_rate()
        self.logger.debug(
            "Type %s is a %s service, taxed at %s.",
            intervention_type.code,
            intervention_type.service_category.value,
            rate,
        )
        if intervention_type.service_category is ServiceCategory.COMFORT:
            self.logger.debug(
                "Type %s bills the standard rate; a reduced rate needs the "
                "type's category changed, not the line's.",
                intervention_type.code,
            )
        return rate

    def aggregate(
        self,
        lines: List[QuoteLine],
        intervention_types: Dict[str, InterventionType],
    ) -> List[QuoteTypeWeekAggregate]:
        """Group priced lines into per-type, per-week totals.

        Args:
            lines (List[QuoteLine]): The priced lines to summarise.
            intervention_types (Dict[str, InterventionType]): The types behind
                those lines, keyed by identifier.

        Returns:
            List[QuoteTypeWeekAggregate]: The totals, in display order.

        Raises:
            KeyError: If a line names a type absent from the mapping.

        Notes:
            - The totals are sums of the amounts already rounded on each line,
              not a re-rounding of an exact sum. That is what makes the weekly
              subtotals on a printed quote add up to its grand total exactly.
            - Unpriced lines are skipped and reported. Including them would make
              the aggregate disagree with the lines beneath it, which on a
              printed quote reads as an arithmetic error rather than as a quote
              that was never fully priced.
        """
        self.logger.debug("Aggregating %d quote line(s).", len(lines))
        buckets: Dict[Tuple[str, int, int], List[QuoteLine]] = {}
        skipped = 0
        for line in lines:
            if not line.is_priced():
                skipped += 1
                continue
            iso_year, iso_week, _ = line.service_date.isocalendar()
            buckets.setdefault(
                (line.intervention_type_id, iso_year, iso_week), []
            ).append(line)
        if skipped:
            self.logger.warning(
                "%d line(s) were left out of the aggregates because they are "
                "not priced.",
                skipped,
            )
        aggregates = [
            self._build(key, bucket, intervention_types)
            for key, bucket in buckets.items()
        ]
        aggregates.sort(key=lambda entry: entry.sort_key())
        self.logger.info(
            "Aggregated %d line(s) into %d type-week total(s).",
            len(lines) - skipped,
            len(aggregates),
        )
        return aggregates

    def price_line(
        self, line: QuoteLine, intervention_type: InterventionType
    ) -> QuoteLine:
        """Return a copy of a line carrying its computed amounts.

        Args:
            line (QuoteLine): The line to price.
            intervention_type (InterventionType): The type it sells.

        Returns:
            QuoteLine: A priced copy. The input is left untouched.

        Notes:
            The effective hourly rate is stored on the line alongside the
            totals, so a quote can show *why* a line cost what it did — a
            customer querying a Sunday visit can be shown the uplifted rate
            rather than being asked to trust the total.
        """
        base_rate = self.base_rate_for(intervention_type)
        multiplier = self.multiplier_for(line.service_date)
        vat_rate = self.vat_rate_for(intervention_type)

        effective_rate = base_rate * multiplier
        total_ht = self._to_cents(effective_rate * line.duration_hours())
        vat_amount = self._to_cents(total_ht * vat_rate)

        self.logger.debug(
            "Priced %r on %s: %s x %s x %sh = %s HT, %s VAT.",
            line.name,
            line.service_date,
            base_rate,
            multiplier,
            line.duration_hours(),
            total_ht,
            vat_amount,
        )
        return line.model_copy(
            update={
                "hourly_rate_ht": self._to_cents(effective_rate),
                "total_ht": total_ht,
                "vat_amount": vat_amount,
                "total_ttc": total_ht + vat_amount,
            }
        )

    def price_quote(
        self, quote: Quote, intervention_types: Dict[str, InterventionType]
    ) -> Quote:
        """Return a copy of a quote with every line priced and aggregated.

        Args:
            quote (Quote): The quote to price.
            intervention_types (Dict[str, InterventionType]): The types behind
                its lines, keyed by identifier.

        Returns:
            Quote: A priced copy, carrying its weekly aggregates.

        Raises:
            MTPricingUnknownInterventionType: If a line names a type that is
                absent from the mapping.

        Notes:
            A missing type is fatal rather than skipped. Pricing a line without
            its type would mean guessing both the rate and the VAT category,
            and a quote that is silently short a line is worse than one that
            refuses to price.
        """
        self.logger.info(
            "Pricing quote %s with %d line(s).", quote.reference, len(quote.lines)
        )
        priced_lines: List[QuoteLine] = []
        for line in quote.lines:
            intervention_type = intervention_types.get(line.intervention_type_id)
            if intervention_type is None:
                self.logger.error(
                    "Quote %s line %r names the unknown type %s.",
                    quote.reference,
                    line.name,
                    line.intervention_type_id,
                )
                raise MTPricingUnknownInterventionType(
                    f"Quote line {line.name!r} names intervention type "
                    f"{line.intervention_type_id!r}, which does not exist."
                )
            priced_lines.append(self.price_line(line, intervention_type))

        aggregates = self.aggregate(priced_lines, intervention_types)
        priced = quote.model_copy(
            update={"lines": priced_lines, "aggregates": aggregates}
        )
        self.logger.info(
            "Quote %s totals %s HT, %s VAT, %s TTC across %d week-type group(s).",
            quote.reference,
            priced.total_ht(),
            priced.total_vat(),
            priced.total_ttc(),
            len(aggregates),
        )
        if not priced.lines:
            self.logger.warning(
                "Quote %s has no lines; it totals nothing and cannot be sent.",
                quote.reference,
            )
        return priced
