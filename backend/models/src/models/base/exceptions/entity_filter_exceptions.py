class MTInvalidEntityFilterException(Exception):
    """Exception raised when a list filter is invalid.

    Notes:
        The base of every concrete filter's family. Each screen's filter names
        its own leaves — a rejected assistant filter must not report itself as
        a customer one — but they all share this ancestor so the API's
        exception-to-status map needs a single row for a rule they all obey.
    """


class MTEntityFilterInvalidFragment(MTInvalidEntityFilterException):
    """Exception raised when a text filter is not a string."""


class MTEntityFilterInvalidFlag(MTInvalidEntityFilterException):
    """Exception raised when a three-state flag is not a boolean.

    Notes:
        Strings are refused rather than coerced. ``"false"`` is truthy, and a
        flag read the wrong way round answers the opposite question in silence
        — on a screen whose whole job is to narrow a list.
    """
