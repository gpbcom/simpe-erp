class MTInvalidInterventionTypeChangeRequestException(Exception):
    """Exception raised when a re-classification payload is invalid."""


class MTInterventionTypeChangeRequestInvalidTypeId(
    MTInvalidInterventionTypeChangeRequestException
):
    """Exception raised when no catalogue entry was named.

    Notes:
        There is no default. "Sell this visit as something else" has to say as
        what; an empty body that silently meant "leave it alone" would answer
        200 to a request that changed nothing, and the manager would go on
        believing the quote had been repriced.
    """
