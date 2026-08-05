class MTInvalidQuoteLineException(Exception):
    """Exception raised when an invalid QuoteLine field is provided."""


class MTQuoteLineInvalidId(MTInvalidQuoteLineException):
    """Exception raised when an invalid ``id`` value is provided."""


class MTQuoteLineInvalidName(MTInvalidQuoteLineException):
    """Exception raised when an invalid ``name`` value is provided."""


class MTQuoteLineInvalidInterventionTypeId(MTInvalidQuoteLineException):
    """Exception raised when an invalid ``intervention_type_id`` is provided."""


class MTQuoteLineInvalidServiceDate(MTInvalidQuoteLineException):
    """Exception raised when an invalid ``service_date`` value is provided."""


class MTQuoteLineInvalidWindow(MTInvalidQuoteLineException):
    """Exception raised when an invalid start or end time is provided."""


class MTQuoteLineInvalidDuration(MTInvalidQuoteLineException):
    """Exception raised when an invalid ``duration_minutes`` is provided."""


class MTQuoteLineInvalidAmount(MTInvalidQuoteLineException):
    """Exception raised when an invalid money amount is provided."""


class MTQuoteLineWindowTooShort(MTInvalidQuoteLineException):
    """Exception raised when the window cannot contain the duration."""
