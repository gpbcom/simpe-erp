class MTInvalidBillingSettingsRequestException(Exception):
    """Exception raised when a billing-settings payload is invalid."""


class MTBillingSettingsRequestInvalidPeriodicity(
    MTInvalidBillingSettingsRequestException
):
    """Exception raised when the requested periodicity is unknown."""


class MTBillingSettingsRequestInvalidPaymentTerms(
    MTInvalidBillingSettingsRequestException
):
    """Exception raised when the requested payment terms are out of range."""


class MTBillingSettingsRequestInvalidPenaltyMultiplier(
    MTInvalidBillingSettingsRequestException
):
    """Exception raised when the requested penalty multiplier is out of range."""


class MTBillingSettingsRequestInvalidIndemnity(
    MTInvalidBillingSettingsRequestException
):
    """Exception raised when the requested recovery indemnity is invalid."""


class MTInvalidBillGenerationRequestException(Exception):
    """Exception raised when a bill-generation payload is invalid."""


class MTBillGenerationRequestInvalidDate(MTInvalidBillGenerationRequestException):
    """Exception raised when the reference date is missing or not a date."""


class MTBillGenerationRequestInvalidCustomers(MTInvalidBillGenerationRequestException):
    """Exception raised when the customer restriction is not a list of ids.

    Notes:
        An empty list is refused rather than read as "every customer". The two
        readings differ by a whole month's invoicing, and a caller that meant
        "all of them" omits the field.
    """


class MTInvalidBillStatusRequestException(Exception):
    """Exception raised when a bill-status payload is invalid."""


class MTBillStatusRequestInvalidStatus(MTInvalidBillStatusRequestException):
    """Exception raised when the requested status is missing or unknown."""


class MTInvalidBillAcceptedRequestException(Exception):
    """Exception raised when a bill-accepted webhook payload is invalid."""


class MTBillAcceptedRequestInvalidId(MTInvalidBillAcceptedRequestException):
    """Exception raised when the announced bill is not identified."""


class MTInvalidBillFilterException(Exception):
    """Exception raised when a bill-list filter is invalid."""


class MTBillFilterInvalidFragment(MTInvalidBillFilterException):
    """Exception raised when a text filter is not a usable fragment."""


class MTBillFilterInvalidFlag(MTInvalidBillFilterException):
    """Exception raised when a three-state flag is not a boolean."""


class MTBillFilterInvalidStatus(MTInvalidBillFilterException):
    """Exception raised when the filtered status is unknown."""


class MTBillFilterInvalidDate(MTInvalidBillFilterException):
    """Exception raised when a period bound is not a date."""


class MTInvalidBillDispatchResponseException(Exception):
    """Exception raised when a bill-dispatch response cannot be built."""


class MTBillDispatchResponseInvalidId(MTInvalidBillDispatchResponseException):
    """Exception raised when the dispatched bill is not identified."""


class MTInvalidBillPaidRequestException(Exception):
    """Exception raised when a bill-paid webhook payload is invalid."""


class MTBillPaidRequestInvalidId(MTInvalidBillPaidRequestException):
    """Exception raised when a bill-paid payload names no invoice."""
