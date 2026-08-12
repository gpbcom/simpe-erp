class MTInvalidQuoteException(Exception):
    """Exception raised when an invalid Quote field is provided."""


class MTQuoteInvalidInterruption(MTInvalidQuoteException):
    """Exception raised when the interruption date cannot apply to the quote."""


class MTQuoteInvalidId(MTInvalidQuoteException):
    """Exception raised when an invalid ``id`` value is provided."""


class MTQuoteInvalidTeamId(MTInvalidQuoteException):
    """Exception raised when the quote does not name the team delivering it.

    Notes:
        Required, not optional. The team decides whose accepted work a planning
        run schedules, and a quote naming none would be one no run ever reads —
        invisible rather than refused, and discovered when somebody asks why a
        family had no visits. The attribution happens once, at creation, and is
        refused there when no team can be determined.
    """


class MTQuoteInvalidCustomerId(MTInvalidQuoteException):
    """Exception raised when an invalid ``customer_id`` value is provided."""


class MTQuoteInvalidReference(MTInvalidQuoteException):
    """Exception raised when an invalid ``reference`` value is provided."""


class MTQuoteInvalidStatus(MTInvalidQuoteException):
    """Exception raised when an invalid ``status`` value is provided."""


class MTQuoteInvalidLines(MTInvalidQuoteException):
    """Exception raised when an invalid ``lines`` list is provided."""


class MTQuoteInvalidAggregates(MTInvalidQuoteException):
    """Exception raised when an invalid ``aggregates`` list is provided."""


class MTQuoteInvalidDate(MTInvalidQuoteException):
    """Exception raised when an invalid date value is provided."""


class MTQuoteInvalidValidity(MTInvalidQuoteException):
    """Exception raised when ``valid_until`` precedes ``issued_on``."""
