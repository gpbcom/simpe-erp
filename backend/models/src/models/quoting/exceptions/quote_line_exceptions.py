class MTInvalidQuoteLineException(Exception):
    """Exception raised when an invalid QuoteLine field is provided."""


class MTQuoteLineInvalidId(MTInvalidQuoteLineException):
    """Exception raised when an invalid ``id`` value is provided."""


class MTQuoteLineInvalidServiceCategory(MTInvalidQuoteLineException):
    """Exception raised when the VAT category is missing or unknown."""


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


class MTQuoteLineInvalidRequiredSkills(MTInvalidQuoteLineException):
    """Exception raised when an invalid ``required_skill_codes`` is given.

    Notes:
        ``None`` on a line inherits the catalogue and an empty list overrides
        it to nothing, exactly as for the certification override beside it.
    """


class MTQuoteLineInvalidRequiredCertifications(MTInvalidQuoteLineException):
    """Exception raised when an invalid ``required_certification_codes`` is given.

    Notes:
        Distinct from the intervention type's own exception even though the
        rule is the same, because the two fields do not mean the same thing:
        ``None`` on a line inherits the catalogue, while the catalogue itself
        has no such state.
    """
