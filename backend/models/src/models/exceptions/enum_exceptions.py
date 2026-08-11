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


class MTRoleNotRankable(MTInvalidEnumException):
    """Exception raised when a role outside the staff ladder is ranked.

    Notes:
        **This guards a privacy hole, not a typo.** The ladder is
        ``hca < manager < admin`` and answers "at least a manager".
        :attr:`~models.enums.UserRole.CUSTOMER` is not above or below any of
        them — it is a different axis — so placing it on the ladder makes
        ``has_at_least(CUSTOMER)`` true for every employee, and a guard written
        the usual way would admit staff to a household's private space.

        Refused loudly here so the mistake is a 500 with this message rather
        than an authorisation check that quietly answers ``True``. Anything
        specific to being a customer compares the role by identity instead.
    """


class MTRoutingKeyMissingCompany(MTInvalidEnumException):
    """Exception raised when a routing key is scoped to no agency.

    Notes:
        An empty identifier would produce ``"quote.submitted."`` — a valid
        topic key that binds to nothing. That is the silent failure the routing
        enumeration exists to prevent, one level down, so it is refused rather
        than published into the void.
    """
