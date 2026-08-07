class MTInvalidEventEnvelopeException(Exception):
    """Exception raised when a broker message is malformed."""


class MTEventEnvelopeInvalidRoutingKey(MTInvalidEventEnvelopeException):
    """Exception raised when the routing key is not a non-empty string."""


class MTEventEnvelopeInvalidPayload(MTInvalidEventEnvelopeException):
    """Exception raised when the payload is not a mapping."""


class MTEventEnvelopeInvalidTimestamp(MTInvalidEventEnvelopeException):
    """Exception raised when the event timestamp is not datetime-like."""


class MTEventEnvelopeInvalidTraceparent(MTInvalidEventEnvelopeException):
    """Exception raised when the carried trace context is malformed.

    Notes:
        Refused rather than dropped. A ``traceparent`` that cannot be parsed
        would silently start a new trace, and the resulting picture — a solve
        that apparently began on its own, with no request behind it — is a
        worse answer than no trace at all, because it looks complete.
    """
