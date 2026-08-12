from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from decimal import Decimal
from typing import ClassVar, Dict, List, Optional, Tuple, Union

# Third-party imports
from pydantic import (
    BaseModel,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

# First-party imports
from models.enums import QuoteStatus
from models.planning.planning_run.unplaced_quote import UnplacedQuote
from models.quoting.exceptions import (
    MTQuoteInvalidAggregates,
    MTQuoteInvalidCustomerId,
    MTQuoteInvalidDate,
    MTQuoteInvalidId,
    MTQuoteInvalidTeamId,
    MTQuoteInvalidInterruption,
    MTQuoteInvalidLines,
    MTQuoteInvalidReference,
    MTQuoteInvalidStatus,
    MTQuoteInvalidValidity,
)
from models.quoting.quote_line import QuoteLine
from models.quoting.quote_type_week_aggregate import QuoteTypeWeekAggregate


class Quote(BaseModel):
    """A priced offer of home care, addressed to one customer.

    Attributes:
        CENTS (ClassVar[Decimal]): The quantum money is rounded to.
        SCHEDULABLE_STATUSES (ClassVar[frozenset]): The statuses whose lines
            feed the planning computation.
        id (Optional[str]): Identifier, populated on read from the store.
        company_id (str): The agency that offers the work.
        team_id (str): The team that will deliver the work.
        reference (str): Human-facing quote number.
        customer_id (str): The customer the offer is addressed to.
        status (QuoteStatus): Where the quote is in its lifecycle.
        lines (List[QuoteLine]): The services offered, priced.
        aggregates (List[QuoteTypeWeekAggregate]): The lines summed by type and
            by ISO week.
        issued_on (Optional[date]): The day the quote was sent.
        valid_until (Optional[date]): The day the offer lapses.
        authored_by (Optional[str]): The account that wrote the quote.
        submitted_at (Optional[datetime]): When it was submitted for validation.
        validated_by (Optional[str]): The account that validated it.
        interrupted_on (Optional[date]): Last day the arrangement is
            delivered. Services dated after it are neither planned nor billed.
        auto_renew (bool): Whether a successor quote is written when this one
            reaches ``valid_until``.
        renewed_from_id (Optional[str]): The quote this one succeeds, when it
            was created by a renewal.
        validated_at (Optional[datetime]): When it was validated.

    Notes:
        - Only an **accepted** quote feeds the planner. A draft is still being
          composed and a rejected one was declined, so scheduling either would
          commit assistants to work nobody agreed to.
        - ``aggregates`` is derived from ``lines`` but stored alongside them.
          Recomputing on read would be cheap; the reason to store it is that a
          reprinted quote must show the figures it showed when it was issued,
          even after a type is renamed or repriced.
        - The four authorship fields exist because a quote is now written by one
          person and approved by another. ``authored_by`` is what scopes an
          assistant's own list; ``validated_by`` is the answer to "who agreed to
          this price?", which the record could not answer at all before — a
          quote simply became accepted, with nothing saying by whom.
    """

    CENTS: ClassVar[Decimal] = Decimal("0.01")
    SCHEDULABLE_STATUSES: ClassVar[frozenset] = frozenset({QuoteStatus.ACCEPTED})

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    company_id: str = Field(description="The agency that offers the work.")
    team_id: str = Field(description="The team that will deliver the work.")
    reference: str = Field(description="Human-facing quote number.")
    customer_id: str = Field(description="The customer the offer is addressed to.")
    status: QuoteStatus = Field(
        default=QuoteStatus.DRAFT,
        description="Where the quote is in its lifecycle.",
    )
    lines: List[QuoteLine] = Field(
        default_factory=list,
        description="The services offered, priced.",
    )
    aggregates: List[QuoteTypeWeekAggregate] = Field(
        default_factory=list,
        description="The lines summed by intervention type and ISO week.",
    )
    issued_on: Optional[date] = Field(
        default=None,
        description="The day the quote was sent.",
    )
    valid_until: Optional[date] = Field(
        default=None,
        description="The day the offer lapses.",
    )
    authored_by: Optional[str] = Field(
        default=None,
        description="The account that wrote the quote.",
    )
    submitted_at: Optional[datetime] = Field(
        default=None,
        description="When it was submitted for validation.",
    )
    validated_by: Optional[str] = Field(
        default=None,
        description="The account that validated it.",
    )
    planning_feedback: Optional[UnplacedQuote] = Field(
        default=None,
        description="Why the last planning could not fit this quote's work.",
    )
    interrupted_on: Optional[date] = Field(
        default=None,
        description="Last day this quote is delivered, or None if it runs on.",
    )
    auto_renew: bool = Field(
        default=False,
        description="Whether a successor is written when this quote expires.",
    )
    renewed_from_id: Optional[str] = Field(
        default=None,
        description="The quote this one was written to succeed, if any.",
    )
    validated_at: Optional[datetime] = Field(
        default=None,
        description="When it was validated.",
    )

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``id`` value.

        Returns:
            Optional[str]: The identifier, or ``None``.

        Raises:
            MTQuoteInvalidId: If ``value`` is neither ``None`` nor a non-empty
                string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("company_id", mode="before")
    def validate_company_id(cls, value: Optional[str]) -> str:
        """Validates that ``company_id`` names the agency offering the work.

        Args:
            value (Optional[str]): Raw ``company_id`` value.

        Returns:
            str: The stripped identifier.

        Raises:
            MTQuoteInvalidId: If ``value`` is not a non-empty string.

        Notes:
            - **Required, where ``authored_by`` is not.** The agency was
              previously reachable only through the author's account, which a
              quote is allowed to lose — an author leaving must not take their
              quotes with them. That left the planner unable to tell whose work a
              quote was, and it selects the work it schedules by exactly this
              field, so an unattributable quote would be scheduled by whichever
              agency ran next.
            - Denormalised rather than joined for the same reason: the join it
              would replace passes through a nullable column.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteInvalidId(
                f"Invalid company_id: {value!r}. Must be a non-empty string "
                f"naming the agency that offers the work."
            )
        return value.strip()

    @field_validator("team_id", mode="before")
    def validate_team_id(cls, value: Optional[str]) -> str:
        """Validates that ``team_id`` names the team delivering the work.

        Args:
            value (Optional[str]): Raw ``team_id`` value.

        Returns:
            str: The stripped identifier.

        Raises:
            MTQuoteInvalidTeamId: If ``value`` is not a non-empty string.

        Notes:
            - **Required, and never carried by a payload.** A caller able to
              name a team could file work into another manager's queue, which is
              the same rule that keeps ``company_id`` off
              :class:`~models.schemas.requests.quoting.quote_create_request.QuoteCreateRequest`.
              The value is decided once, at creation, by the attribution rule.
            - Optional would have been the softer choice and the wrong one. A
              planning run reads its team's accepted work, so a quote naming no
              team is one no run ever sees — invisible rather than refused, and
              found when a family asks why nobody came.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteInvalidTeamId(
                f"Invalid team_id: {value!r}. Must be a non-empty string naming "
                f"the team that will deliver the work."
            )
        return value.strip()

    @field_validator("reference", mode="before")
    def validate_reference(cls, value: Optional[str]) -> str:
        """Validates that ``reference`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``reference`` value.

        Returns:
            str: The stripped, upper-cased reference.

        Raises:
            MTQuoteInvalidReference: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteInvalidReference(
                f"Invalid reference: {value!r}. Must be a non-empty string."
            )
        return value.strip().upper()

    @field_validator("customer_id", mode="before")
    def validate_customer_id(cls, value: Optional[str]) -> str:
        """Validates that ``customer_id`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``customer_id`` value.

        Returns:
            str: The stripped identifier.

        Raises:
            MTQuoteInvalidCustomerId: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteInvalidCustomerId(
                f"Invalid customer_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("status", mode="before")
    def validate_status(cls, value: Union[str, QuoteStatus, None]) -> QuoteStatus:  # noqa: E501
        """Validates that ``status`` is a known quote status.

        Args:
            value (Union[str, QuoteStatus, None]): Raw status. ``None`` falls
                back to :attr:`QuoteStatus.DRAFT`.

        Returns:
            QuoteStatus: The coerced status.

        Raises:
            MTQuoteInvalidStatus: If ``value`` is not a known status.

        Notes:
            The default is the least committal one. A quote whose status was
            lost must not fail open into "accepted", which is what puts work on
            an assistant's calendar.
        """
        if value is None:
            return QuoteStatus.DRAFT
        if isinstance(value, QuoteStatus):
            return value
        try:
            return QuoteStatus(value)
        except ValueError:
            raise MTQuoteInvalidStatus(
                f"Invalid status: {value!r}. Must be one of: "
                f"{', '.join(QuoteStatus.values())}."
            ) from None

    @field_validator("lines", mode="before")
    def validate_lines(cls, value: JsonValue) -> JsonValue:
        """Validates that ``lines`` is a list of quote lines.

        Args:
            value (JsonValue): Raw list of line payloads.

        Returns:
            JsonValue: The list handed back for Pydantic to build.

        Raises:
            MTQuoteInvalidLines: If ``value`` is neither ``None`` nor a list,
                or if an entry is neither a mapping nor a built line.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTQuoteInvalidLines(
                f"Invalid lines: {value!r}. Must be a list or None."
            )
        for entry in value:
            if not isinstance(entry, (QuoteLine, dict)):
                raise MTQuoteInvalidLines(
                    f"Invalid lines entry: {entry!r}. Must be a QuoteLine or a mapping."
                )
        return value

    @field_validator("aggregates", mode="before")
    def validate_aggregates(cls, value: JsonValue) -> JsonValue:
        """Validates that ``aggregates`` is a list of weekly aggregates.

        Args:
            value (JsonValue): Raw list of aggregate payloads.

        Returns:
            JsonValue: The list handed back for Pydantic to build.

        Raises:
            MTQuoteInvalidAggregates: If ``value`` is neither ``None`` nor a
                list, or if an entry is neither a mapping nor a built
                aggregate.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTQuoteInvalidAggregates(
                f"Invalid aggregates: {value!r}. Must be a list or None."
            )
        for entry in value:
            if not isinstance(entry, (QuoteTypeWeekAggregate, dict)):
                raise MTQuoteInvalidAggregates(
                    f"Invalid aggregates entry: {entry!r}. "
                    f"Must be a QuoteTypeWeekAggregate or a mapping."
                )
        return value

    @field_validator("issued_on", "valid_until", mode="before")
    def validate_date(
        cls, value: Union[str, date, datetime, None]
    ) -> Union[str, date, None]:
        """Validates that a date field is date-like or ``None``.

        Args:
            value (Union[str, date, datetime, None]): Raw date value.

        Returns:
            Union[str, date, None]: The value handed back for Pydantic.

        Raises:
            MTQuoteInvalidDate: If ``value`` is neither ``None`` nor date-like.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTQuoteInvalidDate(
            f"Invalid date: {value!r}. Must be a date, an ISO string, or None."
        )

    @field_validator("authored_by", "validated_by", mode="before")
    def validate_actor(cls, value: Optional[str]) -> Optional[str]:
        """Validates that an actor identifier is ``None`` or non-empty.

        Args:
            value (Optional[str]): Raw ``authored_by`` or ``validated_by``
                value.

        Returns:
            Optional[str]: The account identifier, or ``None``.

        Raises:
            MTQuoteInvalidId: If ``value`` is neither ``None`` nor a non-empty
                string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteInvalidId(
                f"Invalid account identifier: {value!r}. "
                "Must be a non-empty "
                f"string or None."
            )
        return value.strip()

    @field_validator("submitted_at", "validated_at", mode="before")
    def validate_moment(
        cls, value: Union[str, datetime, None]
    ) -> Union[str, datetime, None]:
        """Validates that a workflow timestamp is datetime-like or ``None``.

        Args:
            value (Union[str, datetime, None]): Raw timestamp value.

        Returns:
            Union[str, datetime, None]: The value handed back for Pydantic.

        Raises:
            MTQuoteInvalidDate: If ``value`` is neither ``None`` nor
                datetime-like.

        Notes:
            Kept apart from :meth:`validate_date`, which narrows a datetime to
            a date. These two record the instant a decision was taken, and the
            hour of it is exactly what an audit of "who approved this, and
            when?" is asking for.
        """
        if value is None:
            return None
        if isinstance(value, (str, datetime)):
            return value
        raise MTQuoteInvalidDate(
            f"Invalid timestamp: {value!r}. Must be a datetime, an ISO string, or None."
        )

    @model_validator(mode="after")
    def check_validity_window(self) -> Quote:
        """Ensure the offer does not lapse before it is issued.

        Returns:
            Quote: ``self`` for chaining.

        Raises:
            MTQuoteInvalidValidity: If ``valid_until`` precedes ``issued_on``.
        """
        if (
            self.issued_on is not None
            and self.valid_until is not None
            and self.valid_until < self.issued_on
        ):
            raise MTQuoteInvalidValidity(
                f"Invalid valid_until: {self.valid_until}. "
                f"Must be on or after issued_on ({self.issued_on})."
            )
        return self

    @model_validator(mode="after")
    def check_interruption(self) -> Quote:
        """Validates that the interruption falls inside the arrangement.

        Returns:
            Quote: The validated quote.

        Raises:
            MTQuoteInvalidInterruption: If the quote is interrupted before it
                was issued, or before the first service it sells.

        Notes:
            - An interruption before the first service would silence the whole
              quote while leaving it accepted and priced — a quote that costs
              nothing, delivers nothing and still reads as live. Deleting it or
              rejecting it says that; an end date in the past does not.
            - An interruption *after* the last service is allowed and does
              nothing. That is a real thing to record: an arrangement given a
              closing date the work already happens to fit inside.
        """
        if self.interrupted_on is None:
            return self
        if self.issued_on is not None and self.interrupted_on < self.issued_on:
            raise MTQuoteInvalidInterruption(
                f"Invalid interrupted_on: {self.interrupted_on}. "
                f"Must be on or after issued_on ({self.issued_on})."
            )
        first_service = min((line.service_date for line in self.lines), default=None)
        if first_service is not None and self.interrupted_on < first_service:
            raise MTQuoteInvalidInterruption(
                f"Invalid interrupted_on: {self.interrupted_on}. It falls before "
                f"the first service ({first_service}), which would leave an "
                "accepted quote delivering nothing; reject or delete it instead."
            )
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def covers(self, day: date) -> bool:
        """Return whether the arrangement is still running on a day.

        Args:
            day (date): The day to test.

        Returns:
            bool: ``False`` once the quote has been interrupted and the day
            falls after the interruption; ``True`` otherwise.

        Notes:
            The interruption date is **inclusive**: work on the day itself
            still happens. A family cancelling "from the 15th" means the 15th
            is the last visit, and reading it as the first cancelled day would
            take away a visit somebody is expecting.
        """
        return self.interrupted_on is None or day <= self.interrupted_on

    def effective_lines(self) -> List[QuoteLine]:
        """Return the lines this quote still delivers.

        Returns:
            List[QuoteLine]: Every line, minus any dated after an interruption.

        Notes:
            **Interrupted lines are kept, not deleted.** What the customer
            originally agreed to is a record worth having — a family asking why
            they were charged less than the quote says needs to see both
            figures — so the line stays and stops counting instead. Pricing
            aggregates over this list, and the planner builds requirements from
            it, so the shortened quote costs and schedules exactly what it
            still delivers.
        """
        return [line for line in self.lines if self.covers(line.service_date)]

    def is_interrupted(self) -> bool:
        """Return whether an end date has been set on this quote.

        Returns:
            bool: ``True`` when the arrangement has been given a last day.
        """
        return self.interrupted_on is not None

    def is_priced(self) -> bool:
        """Return whether every line carries its computed amounts.

        Returns:
            bool: ``True`` when the quote has lines and all of them are priced.

        Notes:
            An empty quote is **not** priced. Treating it as priced would let a
            quote with nothing on it be accepted and sent for zero euros.
        """
        return bool(self.lines) and all(line.is_priced() for line in self.lines)  # noqa: E501

    def is_schedulable(self) -> bool:
        """Return whether this quote's lines may be planned.

        Returns:
            bool: ``True`` when the quote is accepted and priced.
        """
        return self.status in self.SCHEDULABLE_STATUSES and self.is_priced()

    def total_ht(self) -> Decimal:
        """Return the quote total excluding tax.

        Returns:
            Decimal: The sum of the weekly aggregates, or zero.

        Notes:
            Summed from the aggregates rather than the lines. Both give the
            same figure — the aggregates are themselves sums of rounded line
            amounts — but taking it from the aggregates guarantees the weekly
            subtotals printed on the quote add up to the total printed beneath
            them, whatever rounding happened along the way.
        """
        return sum(
            (aggregate.total_ht for aggregate in self.aggregates),
            Decimal("0.00"),
        )

    def total_vat(self) -> Decimal:
        """Return the total tax on the quote.

        Returns:
            Decimal: The sum of the weekly aggregates, or zero.
        """
        return sum(
            (aggregate.vat_amount for aggregate in self.aggregates),
            Decimal("0.00"),
        )

    def total_ttc(self) -> Decimal:
        """Return the quote total including tax.

        Returns:
            Decimal: The sum of the weekly aggregates, or zero.
        """
        return sum(
            (aggregate.total_ttc for aggregate in self.aggregates),
            Decimal("0.00"),
        )

    def vat_by_rate(self) -> List[Tuple[Decimal, Decimal, Decimal]]:
        """Return the tax broken down by the rate it was charged at.

        Returns:
            List[Tuple[Decimal, Decimal, Decimal]]: One ``(rate, base, tax)``
            triple per distinct VAT rate, ordered by rate.

        Notes:
            - **A quote must state its tax per rate, not as one figure.** Home
              care is billed at two: 5.5% for a necessity service and 20% for a
              comfort one, and a document showing a single "VAT" line gives a
              customer no way to check either — nor an accountant any way to
              post it.
            - The base is summed from the lines rather than recomputed from the
              tax, because the rate is a property of the line's category and
              dividing back out of a rounded tax amount reintroduces the cents
              that rounding just removed.
            - An unpriced line contributes nothing. It has no amounts yet, and
              counting it as zero would state a rate the customer is not being
              charged at.
        """
        bases: Dict[Decimal, Decimal] = {}
        taxes: Dict[Decimal, Decimal] = {}
        for line in self.lines:
            if not line.is_priced():
                continue
            rate = line.service_category.vat_rate()
            bases[rate] = bases.get(rate, Decimal("0.00")) + (
                line.total_ht or Decimal("0.00")
            )
            taxes[rate] = taxes.get(rate, Decimal("0.00")) + (
                line.vat_amount or Decimal("0.00")
            )
        return [(rate, bases[rate], taxes[rate]) for rate in sorted(bases)]

    def sorted_aggregates(self) -> List[QuoteTypeWeekAggregate]:
        """Return the aggregates in display order.

        Returns:
            List[QuoteTypeWeekAggregate]: Ordered by ISO year, ISO week, then
            the intervention type's name.
        """
        return sorted(self.aggregates, key=lambda entry: entry.sort_key())
