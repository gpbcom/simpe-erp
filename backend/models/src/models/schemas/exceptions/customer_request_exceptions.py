class MTInvalidStatusUpdateRequestException(Exception):
    """Exception raised when a registration-status payload is invalid."""


class MTStatusUpdateRequestInvalidStatus(MTInvalidStatusUpdateRequestException):
    """Exception raised when the registration status is not a known one."""


class MTInvalidBillingPeriodicityRequestException(Exception):
    """Exception raised when a billing-periodicity payload is invalid."""


class MTBillingPeriodicityRequestInvalidPeriodicity(
    MTInvalidBillingPeriodicityRequestException
):
    """Exception raised when the periodicity is not a known one.

    Notes:
        ``null`` is **not** an error here: it is how a manager takes an override
        off a customer and puts them back on the agency's own rule. What this
        refuses is a value nobody can bill on.
    """


class MTInvalidCustomerFilterException(Exception):
    """Exception raised when a customer-filter query is invalid."""


class MTCustomerFilterInvalidStatus(MTInvalidCustomerFilterException):
    """Exception raised when the status filter is not a known status."""


class MTCustomerFilterInvalidFragment(MTInvalidCustomerFilterException):
    """Exception raised when a text fragment is not a usable string.

    Notes:
        A blank fragment is not an error — it reads as "this filter is not
        applied", which is what an empty input box means. What this refuses is
        a value of the wrong *type*, which can only come from a caller
        constructing the filter by hand.
    """


class MTCustomerFilterInvalidFlag(MTInvalidCustomerFilterException):
    """Exception raised when a boolean filter is not a boolean.

    Notes:
        Strings are refused rather than coerced, for the reason the account
        flags are: ``"false"`` is truthy, and a filter read the wrong way round
        silently answers a different question than the one asked.
    """


class MTInvalidCustomerProfileUpdateRequestException(Exception):
    """Exception raised when a household's self-service edit is invalid."""


class MTCustomerProfileUpdateRequestInvalidName(
    MTInvalidCustomerProfileUpdateRequestException
):
    """Exception raised when a given or family name is empty."""
