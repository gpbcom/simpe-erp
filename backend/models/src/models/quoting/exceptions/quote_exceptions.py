class MTInvalidQuoteException(Exception):
    """Exception raised when an invalid Quote field is provided."""


class MTQuoteInvalidId(MTInvalidQuoteException):
    """Exception raised when an invalid ``id`` value is provided."""


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
