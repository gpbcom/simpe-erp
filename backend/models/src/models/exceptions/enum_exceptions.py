class MTInvalidEnumException(Exception):
    """Exception raised when a value does not name a member of an enumeration."""


class MTInvalidWeekday(MTInvalidEnumException):
    """Exception raised when an ISO weekday is outside the ``1..7`` range."""
