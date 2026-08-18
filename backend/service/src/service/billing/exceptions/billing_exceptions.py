class MTInvalidBillingServiceException(Exception):
    """Exception raised when the billing service refuses an operation."""


class MTBillNotFound(MTInvalidBillingServiceException):
    """Exception raised when no invoice matches the given identifier."""


class MTBillingRunNotFound(MTInvalidBillingServiceException):
    """Exception raised when no generation run matches the identifier."""


class MTBillAlreadyIssued(MTInvalidBillingServiceException):
    """Exception raised when a customer is already billed for a period.

    Notes:
        A conflict rather than a malformed request: the caller asked for
        something reasonable, and the period simply has an invoice already. In
        an ordinary run this is caught and reported as a skip. It reaches a
        caller only when somebody asked for one customer explicitly.
    """


class MTBillNothingToBill(MTInvalidBillingServiceException):
    """Exception raised when a period holds no billable work.

    Notes:
        Raised only when a caller named the customer. A run over everybody
        treats an empty period as a customer to pass over, because most
        customers have no work in most weeks and refusing the whole run for
        that would make weekly billing impossible.
    """


class MTBillTransitionNotAllowed(MTInvalidBillingServiceException):
    """Exception raised when a status move skips a step in the lifecycle.

    Notes:
        A bill going straight from awaiting validation to paid would skip the
        record of it ever having been approved, and of it ever having been
        sent — the audit trail the four statuses exist to keep.
    """


class MTBillingPeriodInFuture(MTInvalidBillingServiceException):
    """Exception raised when a period being billed has not finished.

    Notes:
        Care that has not happened cannot be invoiced. Refused rather than
        producing an empty document, because the empty document would carry a
        number the series can never reuse.
    """


class MTBillingForbidden(MTInvalidBillingServiceException):
    """Exception raised when a caller may not act on another agency's invoice."""


class MTBillingSettingsUnavailable(MTInvalidBillingServiceException):
    """Exception raised when the invoicing rules cannot be read or seeded.

    Notes:
        Describes the deployment rather than the request: without the rules
        there are no payment terms to print, and an invoice without them is a
        non-conforming document.
    """


class MTBillDocumentUnavailable(MTInvalidBillingServiceException):
    """Exception raised when an invoice's stored document cannot be read.

    Notes:
        The record exists and the number is real. The object store is what did
        not answer. Distinct from a missing invoice so a manager is told to try
        again rather than told their invoice does not exist.
    """


class MTBillDocumentStorageUnavailable(MTInvalidBillingServiceException):
    """Exception raised when no object store is configured to hold documents.

    Notes:
        A deployment that never configured a bucket cannot issue invoices at
        all, because an invoice with no document is a number burnt on nothing.
        Reported as its own failure so the message names the missing piece.
    """
