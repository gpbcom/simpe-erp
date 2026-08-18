class MTInvalidInterventionTypeChangeRequestException(Exception):
    """Exception raised when a re-classification payload is invalid."""


class MTInterventionTypeChangeRequestInvalidTypeId(
    MTInvalidInterventionTypeChangeRequestException
):
    """Exception raised when no catalogue entry was named.

    Notes:
        There is no default. "Sell this visit as something else" has to say as
        what. An empty body that silently meant "leave it alone" would answer
        200 to a request that changed nothing, and the manager would go on
        believing the quote had been repriced.
    """


class MTInvalidInterventionRescheduleRequestException(Exception):
    """Exception raised when a household's reschedule payload is invalid."""


class MTInterventionRescheduleRequestInvalidDay(
    MTInvalidInterventionRescheduleRequestException
):
    """Exception raised when the chosen day is missing or not a date."""


class MTInterventionRescheduleRequestInvalidWindow(
    MTInvalidInterventionRescheduleRequestException
):
    """Exception raised when the offered window is empty or out of the day.

    Notes:
        An end at or before the start is not a narrow window, it is no window:
        the solver would be asked to fit work into nothing and would report the
        visit unplaceable, which reads to the household as their change having
        been ignored.
    """
