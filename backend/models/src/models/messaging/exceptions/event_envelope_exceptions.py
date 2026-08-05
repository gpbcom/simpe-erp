class MTInvalidEventEnvelopeException(Exception):
    """Exception raised when a broker message is malformed."""


class MTEventEnvelopeInvalidRoutingKey(MTInvalidEventEnvelopeException):
    """Exception raised when the routing key is not a non-empty string."""


class MTEventEnvelopeInvalidPayload(MTInvalidEventEnvelopeException):
    """Exception raised when the payload is not a mapping."""


class MTEventEnvelopeInvalidTimestamp(MTInvalidEventEnvelopeException):
    """Exception raised when the event timestamp is not datetime-like."""
