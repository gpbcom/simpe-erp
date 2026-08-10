class MTInvalidQuoteHeaderRequestException(Exception):
    """Exception raised when a quote header edit is invalid."""


class MTQuoteHeaderRequestInvalidReference(MTInvalidQuoteHeaderRequestException):
    """Exception raised when the quote reference is empty or not text."""


class MTQuoteHeaderRequestInvalidCustomer(MTInvalidQuoteHeaderRequestException):
    """Exception raised when the customer identifier is empty or not text."""


class MTQuoteHeaderRequestInvalidDate(MTInvalidQuoteHeaderRequestException):
    """Exception raised when a date is not a date."""


class MTQuoteHeaderRequestInvalidValidity(MTInvalidQuoteHeaderRequestException):
    """Exception raised when a quote would expire before it was issued."""


class MTQuoteHeaderRequestInvalidAutoRenew(MTInvalidQuoteHeaderRequestException):
    """Exception raised when the auto-renew flag is not a boolean."""
