class MTInvoicingConnectorException(Exception):
    """Exception raised when a certified platform cannot be dealt with."""


class MTConnectorUnauthorised(MTInvoicingConnectorException):
    """Exception raised when the platform rejected the credentials.

    Notes:
        Separated from a general failure because it is the only one an agency
        can act on alone: the key is wrong, expired or revoked, and re-entering
        it in the gallery fixes it. Everything else is somebody waiting.
    """


class MTConnectorUnavailable(MTInvoicingConnectorException):
    """Exception raised when the platform could not be reached or answered 5xx.

    Notes:
        Retryable, and deliberately distinct from a rejection. A platform that
        was down is a transmission to attempt again. A platform that refused the
        document is one to fix first.
    """


class MTConnectorRejected(MTInvoicingConnectorException):
    """Exception raised when the platform refused the document itself.

    Notes:
        The expensive one. A rejected invoice has already consumed a number from
        a series that cannot have gaps, so it cannot be edited and re-sent — it
        has to be corrected by a credit note. That is why the connectors submit
        and send as two calls wherever a platform allows it.
    """


class MTConnectorUnsupported(MTInvoicingConnectorException):
    """Exception raised when a platform cannot carry what it was handed.

    Notes:
        Raised rather than silently succeeding. Storecove documents no Chorus
        Pro route at all, and a connector that accepted a public body's invoice
        anyway would send it nowhere — indistinguishable from success until a
        conseil départemental asks where its invoice went.
    """


class MTConnectorNotImplemented(MTInvoicingConnectorException):
    """Exception raised when a supported platform has no connector class.

    Notes:
        The mirror of a missing catalogue entry: a platform the gallery offers
        but nothing can transmit through. A programming error, and an ``MT*``
        so the API boundary can answer it rather than letting a built-in reach
        the client as an unexplained 500.
    """
