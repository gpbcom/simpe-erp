class MTInvalidBillException(Exception):
    """Exception raised when an invalid Bill field is provided."""


class MTBillInvalidId(MTInvalidBillException):
    """Exception raised when an invalid identifier is provided."""


class MTBillInvalidNumber(MTInvalidBillException):
    """Exception raised when an invalid invoice number is provided."""


class MTBillInvalidSequence(MTInvalidBillException):
    """Exception raised when an invalid sequence number or year is provided.

    Notes:
        The pair is what proves the invoice series is unbroken and
        chronological, so a zero, a negative or a non-integer is refused rather
        than stored and discovered at an inspection.
    """


class MTBillInvalidPeriodicity(MTInvalidBillException):
    """Exception raised when the billing periodicity is missing or unknown."""


class MTBillInvalidStatus(MTInvalidBillException):
    """Exception raised when an invalid ``status`` value is provided."""


class MTBillInvalidDate(MTInvalidBillException):
    """Exception raised when an invalid date value is provided."""


class MTBillInvalidMoment(MTInvalidBillException):
    """Exception raised when an invalid timestamp value is provided."""


class MTBillInvalidPeriod(MTInvalidBillException):
    """Exception raised when the billing window does not run forwards."""


class MTBillInvalidDueDate(MTInvalidBillException):
    """Exception raised when the payment is due before the invoice is issued."""


class MTBillInvalidCustomer(MTInvalidBillException):
    """Exception raised when the billed customer is not properly identified."""


class MTBillInvalidAddress(MTInvalidBillException):
    """Exception raised when an invalid billing address is provided."""


class MTBillInvalidLines(MTInvalidBillException):
    """Exception raised when an invalid ``lines`` value is provided."""


class MTBillInvalidLinePeriod(MTInvalidBillException):
    """Exception raised when a line falls outside the period it is billed in.

    Notes:
        This is the whole of the time pro-rata, expressed as an invariant. A
        service that resolved the window wrongly cannot write a bill charging
        the next period's work, because the bill itself refuses to be built.
    """


class MTBillInvalidAmount(MTInvalidBillException):
    """Exception raised when a total is missing or is not a positive decimal."""


class MTBillInvalidTotals(MTInvalidBillException):
    """Exception raised when the stored totals disagree with the lines.

    Notes:
        The totals are stored rather than computed, so that an issued invoice
        reprints identically for ever. That is only safe if they were right when
        they were written, which is what this checks.
    """


class MTBillInvalidDocument(MTInvalidBillException):
    """Exception raised when a bill past validation has no stored document.

    Notes:
        Nobody validates an invoice they cannot read, and a number issued
        against a document that was never produced is a gap in the series.
    """


class MTBillInvalidRecipient(MTInvalidBillException):
    """Exception raised when an invalid billing recipient is provided.

    Notes:
        The recipient is the party that owes the money, which for a funded
        arrangement is not the person cared for. An invoice without one could
        not say who to ask for payment.
    """


class MTBillInvalidOperationNature(MTInvalidBillException):
    """Exception raised when the nature of the operation is not a known one.

    Notes:
        A mandatory mention on a French invoice. Coercing an unknown value to
        "services" would print a guess as a declaration.
    """


class MTBillInvalidShare(MTInvalidBillException):
    """Exception raised when a recipient is asked to pay more than the total.

    Notes:
        A funded share above the invoice total is arithmetic nobody can
        reconcile: the payers' shares would sum past what the customer was
        charged, and the difference would surface as an unexplained credit
        months later.
    """
