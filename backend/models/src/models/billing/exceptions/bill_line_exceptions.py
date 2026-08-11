class MTInvalidBillLineException(Exception):
    """Exception raised when an invalid BillLine field is provided."""


class MTBillLineInvalidId(MTInvalidBillLineException):
    """Exception raised when an invalid identifier is provided."""


class MTBillLineInvalidName(MTInvalidBillLineException):
    """Exception raised when an invalid ``name`` value is provided."""


class MTBillLineInvalidServiceCategory(MTInvalidBillLineException):
    """Exception raised when the VAT category is missing or unknown."""


class MTBillLineInvalidServiceDate(MTInvalidBillLineException):
    """Exception raised when an invalid ``service_date`` value is provided."""


class MTBillLineInvalidWindow(MTInvalidBillLineException):
    """Exception raised when a delivered visit's times do not run forwards."""


class MTBillLineInvalidVisit(MTInvalidBillLineException):
    """Exception raised when a delivered visit is only half recorded.

    Notes:
        A visit has a day, a start and an end, or it has none of them. Half a
        visit would print a date with no hours beside it and leave the reader
        unable to tell an unplanned service from a badly copied one.
    """


class MTBillLineInvalidHca(MTInvalidBillLineException):
    """Exception raised when an invalid assistant name is provided."""


class MTBillLineInvalidDuration(MTInvalidBillLineException):
    """Exception raised when an invalid ``duration_minutes`` is provided."""


class MTBillLineInvalidAmount(MTInvalidBillLineException):
    """Exception raised when an amount is missing or is not a positive decimal.

    Notes:
        Unlike a quote line, a bill line has no unpriced state. An invoice with
        a blank amount column is a legal defect, so the line refuses to exist
        rather than print one.
    """


class MTBillLineInvalidVatRate(MTInvalidBillLineException):
    """Exception raised when the VAT rate is outside the ``0..1`` range."""
