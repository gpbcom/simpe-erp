class MTInvalidCustomerServiceException(Exception):
    """Exception raised when a customer operation fails."""


class MTCustomerNotFound(MTInvalidCustomerServiceException):
    """Exception raised when the named customer does not exist."""


class MTCustomerHasQuotes(MTInvalidCustomerServiceException):
    """Exception raised when deleting a customer who has been quoted.

    Notes:
        A quote is an accounting record. Deleting the customer it was issued to
        would leave it unattributable, so a customer with any quote is stopped
        rather than removed.
    """
