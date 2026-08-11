class MTInvalidEnumException(Exception):
    """Exception raised when a value does not name a member of an enumeration."""


class MTInvalidWeekday(MTInvalidEnumException):
    """Exception raised when an ISO weekday is outside the ``1..7`` range."""


class MTInvalidBillingPeriodicity(MTInvalidEnumException):
    """Exception raised when a billing window is asked for from a non-date.

    Notes:
        Refused rather than coerced. ``window_for`` decides which services a
        customer is charged for, and a string that happened to parse into some
        other day would bill the wrong month without anything looking wrong.
    """


class MTRoutingKeyMissingCompany(MTInvalidEnumException):
    """Exception raised when a routing key is scoped to no agency.

    Notes:
        An empty identifier would produce ``"quote.submitted."`` — a valid
        topic key that binds to nothing. That is the silent failure the routing
        enumeration exists to prevent, one level down, so it is refused rather
        than published into the void.
    """
