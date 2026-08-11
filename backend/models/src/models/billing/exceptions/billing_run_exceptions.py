class MTInvalidBillingRunException(Exception):
    """Exception raised when an invalid BillingRun field is provided."""


class MTBillingRunInvalidId(MTInvalidBillingRunException):
    """Exception raised when an invalid identifier is provided."""


class MTBillingRunInvalidPeriodicity(MTInvalidBillingRunException):
    """Exception raised when the billing periodicity is missing or unknown."""


class MTBillingRunInvalidStatus(MTInvalidBillingRunException):
    """Exception raised when an invalid ``status`` value is provided."""


class MTBillingRunInvalidDate(MTInvalidBillingRunException):
    """Exception raised when an invalid date value is provided."""


class MTBillingRunInvalidMoment(MTInvalidBillingRunException):
    """Exception raised when an invalid timestamp value is provided."""


class MTBillingRunInvalidPeriod(MTInvalidBillingRunException):
    """Exception raised when the billed window does not run forwards."""


class MTBillingRunInvalidIdentifiers(MTInvalidBillingRunException):
    """Exception raised when the recorded outcome is not a list of identifiers.

    Notes:
        The run records which bills it wrote and which customers it could not
        bill. Both lists are what a partial run is read from, so a malformed one
        would leave nobody able to say what actually happened.
    """


class MTBillingRunInvalidError(MTInvalidBillingRunException):
    """Exception raised when an invalid failure message is provided."""
