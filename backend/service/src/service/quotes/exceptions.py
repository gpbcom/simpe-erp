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
