from __future__ import annotations

# Standard library imports
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Dict, List, Optional, Tuple, Union

# Third-party imports
from pydantic import (  # noqa: E501
    BaseModel,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

# First-party imports
from models.billing.bill_line import BillLine
from models.billing.exceptions import (
    MTBillInvalidAddress,
    MTBillInvalidAmount,
    MTBillInvalidCustomer,
    MTBillInvalidDate,
    MTBillInvalidDocument,
    MTBillInvalidDueDate,
    MTBillInvalidId,
    MTBillInvalidLinePeriod,
    MTBillInvalidLines,
    MTBillInvalidMoment,
    MTBillInvalidNumber,
    MTBillInvalidPeriod,
    MTBillInvalidPeriodicity,
    MTBillInvalidSequence,
    MTBillInvalidStatus,
    MTBillInvalidTotals,
)
from models.enums import BillingPeriodicity, BillStatus
from models.geo.postal_address import PostalAddress


class Bill(BaseModel):
    """One invoice: what a customer owes for the visits made in one period.

    Attributes:
        CENTS (ClassVar[Decimal]): The quantum money is rounded to.
        CURRENCY (ClassVar[str]): The currency every amount is expressed in.
        MIN_SEQUENCE_YEAR (ClassVar[int]): Earliest year a series may run in.
        MAX_SEQUENCE_YEAR (ClassVar[int]): Latest year a series may run in.
        MONEY_FIELDS (ClassVar[Tuple[str, ...]]): The fields holding a total.
        id (Optional[str]): Identifier, populated on read from the store.
        company_id (str): The agency that issued it.
        customer_id (str): The customer it is addressed to.
        billing_run_id (Optional[str]): The run that produced it.
        number (str): Human-facing invoice number.
        sequence (int): Position in the agency's series for the year.
        sequence_year (int): The year the series belongs to.
        periodicity (BillingPeriodicity): The rule the window came from.
        period_start (date): First day billed.
        period_end (date): Last day billed.
        issued_on (date): The invoice date.
        due_on (date): The day payment falls due.
        status (BillStatus): Where the bill has reached commercially.
        customer_full_name (str): The customer's name, as addressed.
        customer_address (PostalAddress): Where the invoice was addressed.
        lines (List[BillLine]): The visits charged.
        total_ht (Decimal): Invoice total excluding tax.
        total_vat (Decimal): Total tax.
        total_ttc (Decimal): Invoice total including tax.
        document_key (Optional[str]): Where the rendered document is stored.
        generated_by (Optional[str]): The account that ran the generation.
        validated_by (Optional[str]): The account that approved it.
        validated_at (Optional[datetime]): When it was approved.
        sent_at (Optional[datetime]): When it was emailed to the customer.
        paid_on (Optional[date]): The day it was settled.
        created_at (Optional[datetime]): When the record was written.
        updated_at (Optional[datetime]): When it last changed.

    Notes:
        - **The bill lists visits, never quotes.** Each line names a service, a
          day and — where a planning run placed it — an assistant and the hours
          worked. No quote reference and no quote total appears anywhere,
          because a customer's question is "what was done for me in March", and
          a document answering "quote D-2648, 1 240 €" answers a different one.
        - **The totals are stored, not computed.** :class:`~models.quoting.quote.Quote`
          computes its own, which is exactly why they are absent from its
          serialised form. An invoice must reprint identically for ever and its
          totals must be readable by a client, so they are persisted — the same
          reasoning that already stores a quote *line*'s four money fields. What
          makes that safe is :meth:`check_totals`, which proves they agreed with
          the lines at the moment they were written.
        - **The customer's name and address are copies**, like the assistant's
          name on an intervention. A customer who moves must not retroactively
          change where last quarter's invoice was addressed.
        - **``number`` and ``sequence`` are the legal series.** French invoicing
          requires an unbroken, chronological sequence per issuer, which is why
          the position is a stored integer and not something derived from a
          creation timestamp: a row inserted out of order would leave a gap
          nobody could explain.
        - There is no cancelled state. A mistaken invoice is corrected by a
          credit note, which is a document of its own, because a number
          withdrawn from the series is exactly the gap the series forbids.
    """

    CENTS: ClassVar[Decimal] = Decimal("0.01")
    CURRENCY: ClassVar[str] = "EUR"
    MIN_SEQUENCE_YEAR: ClassVar[int] = 1970
    MAX_SEQUENCE_YEAR: ClassVar[int] = 9999
    MONEY_FIELDS: ClassVar[Tuple[str, ...]] = (
        "total_ht",
        "total_vat",
        "total_ttc",
    )

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    company_id: str = Field(description="The agency that issued it.")
    customer_id: str = Field(description="The customer it is addressed to.")
    billing_run_id: Optional[str] = Field(
        default=None,
        description="The run that produced it.",
    )
    number: str = Field(description="Human-facing invoice number.")
    sequence: int = Field(description="Position in the agency's yearly series.")
    sequence_year: int = Field(description="The year the series belongs to.")
    periodicity: BillingPeriodicity = Field(
        description="The rule the billed window came from.",
    )
    period_start: date = Field(description="First day billed.")
    period_end: date = Field(description="Last day billed.")
    issued_on: date = Field(description="The invoice date.")
    due_on: date = Field(description="The day payment falls due.")
    status: BillStatus = Field(
        default=BillStatus.TO_BE_VALIDATED,
        description="Where the bill has reached commercially.",
    )
    customer_full_name: str = Field(description="The customer's name.")
    customer_address: PostalAddress = Field(
        description="Where the invoice was addressed.",
    )
    lines: List[BillLine] = Field(
        default_factory=list,
        description="The visits charged.",
    )
    total_ht: Decimal = Field(description="Invoice total excluding tax.")
    total_vat: Decimal = Field(description="Total tax.")
    total_ttc: Decimal = Field(description="Invoice total including tax.")
    document_key: Optional[str] = Field(
        default=None,
        description="Where the rendered document is stored.",
    )
    generated_by: Optional[str] = Field(
        default=None,
        description="The account that ran the generation.",
    )
    validated_by: Optional[str] = Field(
        default=None,
        description="The account that approved it.",
    )
    validated_at: Optional[datetime] = Field(
        default=None,
        description="When it was approved.",
    )
    sent_at: Optional[datetime] = Field(
        default=None,
        description="When it was emailed to the customer.",
    )
    paid_on: Optional[date] = Field(
        default=None,
        description="The day it was settled.",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="When the record was written.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="When it last changed.",
    )

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator(
        "id",
        "billing_run_id",
        "document_key",
        "generated_by",
        "validated_by",
        mode="before",
    )
    def validate_optional_identifier(cls, value: Optional[str]) -> Optional[str]:  # noqa: E501
        """Validates that an optional identifier is ``None`` or non-empty.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            Optional[str]: The stripped identifier, or ``None``.

        Raises:
            MTBillInvalidId: If ``value`` is neither ``None`` nor a non-empty
                string.

        Notes:
            ``generated_by`` and ``validated_by`` are audit strings rather than
            foreign keys, deliberately: "who approved this invoice?" outlives
            the account of whoever left the agency.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTBillInvalidId(
                f"Invalid identifier: {value!r}. "  # noqa: E501
                "Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("company_id", "customer_id", mode="before")
    def validate_identifier(cls, value: Optional[str]) -> str:
        """Validates that a required identifier is a non-empty string.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTBillInvalidId: If ``value`` is not a non-empty string.

        Notes:
            The agency is required and is not reachable through the customer: a
            customer record carries no agency of its own, so an invoice that did
            not name its issuer could not be listed, scoped or numbered.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTBillInvalidId(
                f"Invalid identifier: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("number", mode="before")
    def validate_number(cls, value: Optional[str]) -> str:
        """Validates that ``number`` is a non-empty invoice number.

        Args:
            value (Optional[str]): Raw number.

        Returns:
            str: The stripped, upper-cased number.

        Raises:
            MTBillInvalidNumber: If ``value`` is not a non-empty string.

        Notes:
            Upper-cased so ``fa-2026-000012`` and ``FA-2026-000012`` cannot both
            exist and look like two invoices. The quote reference is normalised
            the same way and for the same reason.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTBillInvalidNumber(
                f"Invalid number: {value!r}. Must be a non-empty string."
            )
        return value.strip().upper()

    @field_validator("customer_full_name", mode="before")
    def validate_customer_full_name(cls, value: Optional[str]) -> str:
        """Validates that the billed customer is named.

        Args:
            value (Optional[str]): Raw name.

        Returns:
            str: The stripped name.

        Raises:
            MTBillInvalidCustomer: If ``value`` is not a non-empty string.

        Notes:
            An invoice must identify the person it is addressed to. Falling back
            to the identifier would print a UUID on a document somebody has to
            recognise as their own.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTBillInvalidCustomer(
                f"Invalid customer_full_name: {value!r}. "  # noqa: E501
                "Must be a non-empty string."
            )
        return value.strip()

    @field_validator("customer_address", mode="before")
    def validate_customer_address(
        cls, value: Union[PostalAddress, Dict[str, JsonValue], None]
    ) -> Union[PostalAddress, Dict[str, JsonValue]]:
        """Validates that ``customer_address`` is an address or a mapping.

        Args:
            value (Union[PostalAddress, Dict[str, JsonValue], None]): Raw
                address value.

        Returns:
            Union[PostalAddress, Dict[str, JsonValue]]: The value handed back
            for Pydantic to build.

        Raises:
            MTBillInvalidAddress: If ``value`` is neither a
                :class:`~models.geo.postal_address.PostalAddress` nor a mapping.
        """
        if value is None or not isinstance(value, (PostalAddress, dict)):
            raise MTBillInvalidAddress(
                f"Invalid customer_address: {value!r}. "  # noqa: E501
                "Must be a PostalAddress "
                f"or a mapping."
            )
        return value

    @field_validator("sequence", mode="before")
    def validate_sequence(cls, value: Optional[Union[int, str]]) -> int:
        """Validates that ``sequence`` is a strictly positive position.

        Args:
            value (Optional[Union[int, str]]): Raw sequence number.

        Returns:
            int: The validated position.

        Raises:
            MTBillInvalidSequence: If ``value`` is not a strictly positive
                integer.

        Notes:
            Numbering starts at one. A zero would be a position no invoice
            occupies, and the series is read as a count of documents issued.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTBillInvalidSequence(
                f"Invalid sequence: {value!r}. "  # noqa: E501
                "Must be a strictly positive integer."
            )
        if value <= 0:
            raise MTBillInvalidSequence(
                f"Invalid sequence: {value!r}. "  # noqa: E501
                "Must be strictly positive."
            )
        return value

    @field_validator("sequence_year", mode="before")
    def validate_sequence_year(cls, value: Optional[Union[int, str]]) -> int:
        """Validates that ``sequence_year`` is a plausible calendar year.

        Args:
            value (Optional[Union[int, str]]): Raw year.

        Returns:
            int: The validated year.

        Raises:
            MTBillInvalidSequence: If ``value`` is not a four-digit year.

        Notes:
            Bounded rather than free, because the year is half of what makes a
            number unique. A typo landing in year 202 would start a second
            series nobody would find again.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTBillInvalidSequence(
                f"Invalid sequence_year: {value!r}. "  # noqa: E501
                "Must be a whole year."
            )
        if not cls.MIN_SEQUENCE_YEAR <= value <= cls.MAX_SEQUENCE_YEAR:
            raise MTBillInvalidSequence(
                f"Invalid sequence_year: {value!r}. Must be within "
                f"{cls.MIN_SEQUENCE_YEAR}..{cls.MAX_SEQUENCE_YEAR}."
            )
        return value

    @field_validator("periodicity", mode="before")
    def validate_periodicity(
        cls, value: Optional[Union[str, BillingPeriodicity]]
    ) -> BillingPeriodicity:
        """Validates that ``periodicity`` names a known billing rule.

        Args:
            value (Union[str, BillingPeriodicity, None]): Raw periodicity.

        Returns:
            BillingPeriodicity: The coerced periodicity.

        Raises:
            MTBillInvalidPeriodicity: If ``value`` is missing or unknown.

        Notes:
            Stored on the bill as a snapshot of the setting used, so an agency
            that switches from weekly to monthly can still explain why last
            March produced four invoices.
        """
        if isinstance(value, BillingPeriodicity):
            return value
        try:
            return BillingPeriodicity(value)
        except ValueError:
            raise MTBillInvalidPeriodicity(
                f"Invalid periodicity: {value!r}. Must be one of: "
                f"{', '.join(BillingPeriodicity.values())}."
            ) from None

    @field_validator("status", mode="before")
    def validate_status(cls, value: Optional[Union[str, BillStatus]]) -> BillStatus:  # noqa: E501
        """Validates that ``status`` is a known bill status.

        Args:
            value (Optional[Union[str, BillStatus]]): Raw status. ``None`` falls
                back to :attr:`BillStatus.TO_BE_VALIDATED`.

        Returns:
            BillStatus: The coerced status.

        Raises:
            MTBillInvalidStatus: If ``value`` is not a known status.

        Notes:
            The fallback is the *first* status and never a later one. A missing
            value defaulting to anything past validation would put an invoice
            nobody approved into the post.
        """
        if value is None:
            return BillStatus.TO_BE_VALIDATED
        if isinstance(value, BillStatus):
            return value
        try:
            return BillStatus(value)
        except ValueError:
            raise MTBillInvalidStatus(
                f"Invalid status: {value!r}. Must be one of: "
                f"{', '.join(BillStatus.values())}."
            ) from None

    @field_validator("period_start", "period_end", "issued_on", "due_on", mode="before")
    def validate_required_date(
        cls,
        value: Optional[
            Union[
                str,
                date,
                datetime,
            ]
        ],
    ) -> Union[str, date]:
        """Validates that a mandatory date field is date-like.

        Args:
            value (Optional[Union[str, date, datetime,]]): Raw date value.

        Returns:
            Union[str, date]: The value handed back for Pydantic to parse.

        Raises:
            MTBillInvalidDate: If ``value`` is missing or is not date-like.

        Notes:
            Separate from ``paid_on``'s validator rather than shared with it,
            because a missing value means opposite things: an invoice with no
            period or no issue date is malformed, while one with no settlement
            date is simply unpaid. Refusing the first here is also what keeps
            the failure the model's own, mappable exception rather than a
            generic validation error the API answers as an unlabelled 422.
        """
        if value is None:
            raise MTBillInvalidDate(
                "Invalid date: the period, the invoice date and the due date "
                "are all required."
            )
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTBillInvalidDate(
            f"Invalid date: {value!r}. Must be a date or an ISO string."
        )

    @field_validator("paid_on", mode="before")
    def validate_paid_on(
        cls,
        value: Optional[
            Union[
                str,
                date,
                datetime,
            ]
        ],
    ) -> Optional[Union[str, date]]:
        """Validates that ``paid_on`` is date-like or ``None``.

        Args:
            value (Optional[Union[str, date, datetime,]]): Raw date value.

        Returns:
            Union[str, date]: The value handed back for Pydantic to parse.

        Raises:
            MTBillInvalidDate: If ``value`` is not date-like.

        Notes:
            ``None`` is the ordinary case for most of an invoice's life.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTBillInvalidDate(
            f"Invalid paid_on: {value!r}. Must be a date or an ISO string."
        )

    @field_validator(
        "validated_at", "sent_at", "created_at", "updated_at", mode="before"
    )
    def validate_moment(
        cls, value: Union[str, datetime, None]
    ) -> Union[str, datetime, None]:
        """Validates that a timestamp is datetime-like or ``None``.

        Args:
            value (Union[str, datetime, None]): Raw timestamp.

        Returns:
            Union[str, datetime, None]: The value handed back for Pydantic to
            parse.

        Raises:
            MTBillInvalidMoment: If ``value`` is neither ``None`` nor
                datetime-like.
        """
        if value is None:
            return None
        if isinstance(value, (str, datetime)):
            return value
        raise MTBillInvalidMoment(
            f"Invalid moment: {value!r}. Must be a datetime or an ISO string."
        )

    @field_validator("lines", mode="before")
    def validate_lines(cls, value: JsonValue) -> JsonValue:
        """Validates that ``lines`` is a list of charges.

        Args:
            value (JsonValue): Raw ``lines`` value.

        Returns:
            JsonValue: The value handed back for Pydantic to build.

        Raises:
            MTBillInvalidLines: If ``value`` is not a list.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTBillInvalidLines(
                f"Invalid lines: {value!r}. Must be a list of bill lines."
            )
        return value

    @field_validator(*MONEY_FIELDS, mode="before")
    def validate_total(cls, value: Union[int, float, str, Decimal, None]) -> Decimal:  # noqa: E501
        """Validates that a total is a non-negative decimal.

        Args:
            value (Union[int, float, str, Decimal, None]): Raw total.

        Returns:
            Decimal: The total as a :class:`~decimal.Decimal`.

        Raises:
            MTBillInvalidAmount: If ``value`` is missing, unreadable, or
                negative.

        Notes:
            Routed through ``str`` so a JSON float keeps its exact value. Money
            never touches a float in this application.
        """
        if value is None:
            raise MTBillInvalidAmount("Invalid total: a total is required on a bill.")
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):  # noqa: E501
            raise MTBillInvalidAmount(
                f"Invalid total: {value!r}. Must be a non-negative decimal."
            )
        try:
            coerced = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise MTBillInvalidAmount(
                f"Invalid total: {value!r}. Must be a non-negative decimal."
            ) from None
        if not coerced.is_finite() or coerced < 0:
            raise MTBillInvalidAmount(
                f"Invalid total: {coerced!r}. Must be non-negative."
            )
        return coerced

    @model_validator(mode="after")
    def check_period(self) -> Bill:
        """Ensure the billed window runs forwards.

        Returns:
            Bill: ``self`` for chaining.

        Raises:
            MTBillInvalidPeriod: If ``period_end`` falls before ``period_start``.

        Notes:
            Both bounds are inclusive, so a single-day period is legitimate and
            only a reversed one is refused.
        """
        if self.period_end < self.period_start:
            raise MTBillInvalidPeriod(
                f"Invalid period_end: {self.period_end}. "
                f"Must not be before period_start ({self.period_start})."
            )
        return self

    @model_validator(mode="after")
    def check_due_date(self) -> Bill:
        """Ensure payment is not due before the invoice was issued.

        Returns:
            Bill: ``self`` for chaining.

        Raises:
            MTBillInvalidDueDate: If ``due_on`` falls before ``issued_on``.

        Notes:
            An invoice already overdue on the day it is written would start its
            own late-payment penalties running, which is the one thing the
            printed terms promise it will not do.
        """
        if self.due_on < self.issued_on:
            raise MTBillInvalidDueDate(
                f"Invalid due_on: {self.due_on}. "
                f"Must not be before issued_on ({self.issued_on})."
            )
        return self

    @model_validator(mode="after")
    def check_lines_in_period(self) -> Bill:
        """Ensure every charge falls inside the period being billed.

        Returns:
            Bill: ``self`` for chaining.

        Raises:
            MTBillInvalidLinePeriod: If a line's ``service_date`` falls outside
                ``[period_start, period_end]``.

        Notes:
            **This is the time pro-rata, expressed as an invariant.** A quote
            line is a single dated service, so "only the part inside the window
            is billed" is a date filter — and a filter is something a service can
            get wrong quietly. Checked here as well, a caller that resolved the
            window badly cannot write a bill charging the next period's work: the
            bill refuses to be built at all, months before anybody reconciles it.
        """
        for line in self.lines:
            if not self.period_start <= line.service_date <= self.period_end:
                raise MTBillInvalidLinePeriod(
                    f"Invalid line {line.name!r} dated {line.service_date}. "
                    f"Must fall within {self.period_start}..{self.period_end}."
                )
        return self

    @model_validator(mode="after")
    def check_totals(self) -> Bill:
        """Ensure the stored totals are the sums of the lines.

        Returns:
            Bill: ``self`` for chaining.

        Raises:
            MTBillInvalidTotals: If a total disagrees with the lines.

        Notes:
            The totals are stored so an issued invoice reprints identically for
            ever. That is only safe if they were right when they were written,
            and this is what proves it: a rounding path that drifted, or a line
            added without the totals being recomputed, is caught here rather
            than by a customer adding up the column themselves.
        """
        expected = (
            sum((line.total_ht for line in self.lines), Decimal("0.00")),
            sum((line.vat_amount for line in self.lines), Decimal("0.00")),
            sum((line.total_ttc for line in self.lines), Decimal("0.00")),
        )
        actual = (self.total_ht, self.total_vat, self.total_ttc)
        for name, stored, computed in zip(self.MONEY_FIELDS, actual, expected):
            if stored != computed:
                raise MTBillInvalidTotals(
                    f"Invalid {name}: {stored}. The lines sum to {computed}."
                )
        return self

    @model_validator(mode="after")
    def check_document(self) -> Bill:
        """Ensure a bill past validation has a document behind it.

        Returns:
            Bill: ``self`` for chaining.

        Raises:
            MTBillInvalidDocument: If the bill has moved past
                :attr:`BillStatus.TO_BE_VALIDATED` with no ``document_key``.

        Notes:
            Nobody validates an invoice they cannot read, and a number issued
            against a document that was never produced is a gap in a series that
            forbids gaps. A bill awaiting validation may legitimately have none
            for the instant between its record being written and its document
            being stored.
        """
        if self.status is not BillStatus.TO_BE_VALIDATED and not self.document_key:  # noqa: E501
            raise MTBillInvalidDocument(
                f"Invalid document_key: a bill in "
                f"{self.status.value!r} must "  # noqa: E501
                f"have a stored document."
            )
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def vat_by_rate(self) -> List[Tuple[Decimal, Decimal, Decimal]]:
        """Return the tax broken down by the rate it was charged at.

        Returns:
            List[Tuple[Decimal, Decimal, Decimal]]: One ``(rate, base, tax)``
            triple per distinct VAT rate, ordered by rate.

        Notes:
            A French invoice must state the tax per rate rather than as one
            figure, and a home-care invoice routinely carries both — assistance
            given for necessity at 5.5% beside comfort work at 20%. Grouped on
            the line's **stored** rate, not on its category, so a reprint after
            a statutory change still shows the rates the customer was charged.
        """
        bases: Dict[Decimal, Decimal] = {}
        taxes: Dict[Decimal, Decimal] = {}
        for line in self.lines:
            bases[line.vat_rate] = bases.get(line.vat_rate, Decimal("0.00")) + (
                line.total_ht
            )
            taxes[line.vat_rate] = taxes.get(line.vat_rate, Decimal("0.00")) + (
                line.vat_amount
            )
        return [(rate, bases[rate], taxes[rate]) for rate in sorted(bases)]

    def total_minutes(self) -> int:
        """Return how much care this invoice charges for.

        Returns:
            int: The summed duration of every line, in minutes.
        """
        return sum(line.duration_minutes for line in self.lines)

    def sorted_lines(self) -> List[BillLine]:
        """Return the charges in the order they are printed.

        Returns:
            List[BillLine]: The lines, earliest first.

        Notes:
            A customer reads an invoice as a diary of their month, so the order
            is chronological rather than by service or by amount. Lines the
            planner never placed have no time of day and sort to the start of
            their own day, which is where a reader looks for them.
        """
        return sorted(
            self.lines,
            key=lambda line: (
                line.service_date,
                line.start_time if line.start_time else time.min,
                line.name,
            ),
        )

    def is_empty(self) -> bool:
        """Return whether there is anything to charge.

        Returns:
            bool: ``True`` when the bill carries no line.

        Notes:
            An empty bill is never issued. Burning a number on a document
            charging nothing would put a gap in the series in all but name, and
            a customer with no visits in a period has simply nothing to pay.
        """
        return not self.lines

    def is_sent(self) -> bool:
        """Return whether the customer has been sent this invoice.

        Returns:
            bool: ``True`` once it has been emailed.

        Notes:
            Read from ``sent_at`` rather than from the status, and the two can
            legitimately disagree: a bill a manager pushed to
            :attr:`BillStatus.WAITING_PAYMENT` by hand because the mail server
            was down is awaited but was never sent from here.
        """
        return self.sent_at is not None

    def describe_period(self) -> str:
        """Return the billed window, as printed on the document.

        Returns:
            str: The window in ``DD/MM/YYYY - DD/MM/YYYY`` form.

        Notes:
            Printed because French law requires the date of performance whenever
            it differs from the invoice date, which for a periodic invoice it
            always does.
        """
        return f"{self.period_start:%d/%m/%Y} - {self.period_end:%d/%m/%Y}"
