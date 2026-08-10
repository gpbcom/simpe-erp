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


class MTCustomerNotPromotable(MTInvalidCustomerServiceException):
    """Exception raised when promoting a customer who is not a prospect.

    Notes:
        Promotion is the one status change with a rule, and this is where the
        rule lives. ``set_status`` still accepts any transition — a manager may
        stop an active customer, or move a stopped one back — because those are
        ordinary corrections. Promotion is not: it is the act that makes the
        planner start routing to somebody's door, so it may only be applied to
        a prospect.

        Promoting an already-active customer is refused rather than treated as
        a no-op. A button that silently succeeds when it did nothing is a button
        somebody presses twice, and then wonders which press took effect.
    """
