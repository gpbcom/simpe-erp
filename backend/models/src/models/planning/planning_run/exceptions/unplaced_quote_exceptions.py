class MTInvalidUnplacedQuoteException(Exception):
    """Exception raised when a quote's unplaced-work summary is invalid."""


class MTUnplacedQuoteInvalidReference(MTInvalidUnplacedQuoteException):
    """Exception raised when the quote reference is empty or not text."""


class MTUnplacedQuoteInvalidCustomer(MTInvalidUnplacedQuoteException):
    """Exception raised when the customer name is not text."""


class MTUnplacedQuoteInvalidVisits(MTInvalidUnplacedQuoteException):
    """Exception raised when a quote is reported with no unplaced visit."""
