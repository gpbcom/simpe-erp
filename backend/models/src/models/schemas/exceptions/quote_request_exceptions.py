class MTInvalidQuoteCreateRequestException(Exception):
    """Exception raised when a quote-creation payload is invalid."""


class MTQuoteCreateRequestInvalidReference(MTInvalidQuoteCreateRequestException):
    """Exception raised when the quote number is missing or blank.

    Notes:
        The reference is what a customer quotes back on the phone and what the
        stored quote is unique on. Generating one here would produce a number
        the person who asked for the quote has never seen.
    """


class MTQuoteCreateRequestInvalidCustomerId(MTInvalidQuoteCreateRequestException):
    """Exception raised when no customer was named.

    Notes:
        A quote is an offer addressed to somebody. There is no sensible default
        recipient, and one invented here would produce a priced offer nobody
        could be shown.
    """


class MTQuoteCreateRequestInvalidLines(MTInvalidQuoteCreateRequestException):
    """Exception raised when the services offered are not a list.

    Notes:
        An empty list is allowed — a quote is composed line by line, and the
        first save is often before any service has been chosen. Something that
        is not a list at all is not.
    """


class MTInvalidQuoteLinesRequestException(Exception):
    """Exception raised when a line-replacement payload is invalid."""


class MTQuoteLinesRequestInvalidLines(MTInvalidQuoteLinesRequestException):
    """Exception raised when the replacement services are not a list.

    Notes:
        Distinct from the creation payload's exception, though the check is the
        same, because the two payloads are answered by different routes and a
        caller reading the message should be told which one it failed.
    """


class MTInvalidQuoteRescheduleRequestException(Exception):
    """Exception raised when a reschedule payload is invalid."""


class MTQuoteRescheduleRequestInvalidLineId(MTInvalidQuoteRescheduleRequestException):
    """Exception raised when the line to move is not named."""


class MTQuoteRescheduleRequestInvalidDay(MTInvalidQuoteRescheduleRequestException):
    """Exception raised when the new day is not a date."""


class MTQuoteRescheduleRequestInvalidWindow(MTInvalidQuoteRescheduleRequestException):
    """Exception raised when the offered window is not a usable window.

    Notes:
        Whether it is *wide enough* for the work is decided by the quote line,
        which is the thing that knows how long the service takes. This covers
        only what the payload can judge on its own: real minutes, in order.
    """


class MTInvalidQuoteTeamRequestException(Exception):
    """Exception raised when a payload moving a quote's team is invalid."""


class MTQuoteTeamRequestInvalidTeamId(MTInvalidQuoteTeamRequestException):
    """Exception raised when the destination team is not named."""
