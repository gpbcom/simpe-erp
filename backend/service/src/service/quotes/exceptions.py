class MTInvalidPricingException(Exception):
    """Exception raised when a quote cannot be priced."""


class MTPricingUnknownInterventionType(MTInvalidPricingException):
    """Exception raised when a line names an intervention type that is gone."""


class MTQuoteNotFound(MTInvalidPricingException):
    """Exception raised when the named quote does not exist."""


class MTQuoteNotPriced(MTInvalidPricingException):
    """Exception raised when a quote must be priced before the next step."""


class MTQuoteNotEditable(MTInvalidPricingException):
    """Exception raised when a quote past draft is edited."""


class MTQuoteForbidden(MTInvalidPricingException):
    """Exception raised when a caller acts on a quote that is not theirs.

    Notes:
        Row-level, not route-level. A route guard proves the caller is an
        assistant; only comparing the quote's stored author against the caller
        stops one assistant submitting or reading another's work.
    """


class MTQuoteLineNotFound(MTInvalidPricingException):
    """Exception raised when a quote does not carry the line named.

    Notes:
        Distinct from :class:`MTQuoteNotFound`, which says the quote itself is
        absent. A caller told only "not found" cannot tell whether they have
        the wrong quote or a stale line — and the second happens routinely,
        because the offered slots a screen is showing were computed against the
        quote as it stood when the planner last ran.
    """


class MTQuoteUnassignable(MTInvalidPricingException):
    """Exception raised when no team can be given a new quote.

    Notes:
        A quote exists to become visits, and a visit is delivered by a team. A
        quote nothing could be attributed to would be accepted, priced, sent to
        a household — and then read by no planning run, because every run asks
        for one team's work. It would go quiet rather than wrong, which is why
        this is a refusal at creation rather than a nullable column.

        Answered as a **422**, and the message says which of the causes applied:
        the household could not be located, or the company has no team to give
        the work to. They are fixed on two different screens by two different
        people, and "the quote could not be assigned" sends somebody to look for
        both.
    """


class MTQuoteTeamForbidden(MTInvalidPricingException):
    """Exception raised when a caller moves a quote to a team not theirs.

    Notes:
        Distinct from :class:`MTQuoteForbidden`, which is about authorship. This
        one is about *destination*: a manager may move work between the teams
        they run, and moving it into somebody else's queue would commit
        assistants they do not manage to work they never agreed to take.
    """
