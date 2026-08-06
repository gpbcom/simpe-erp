class MTInvalidMessagingException(Exception):
    """Exception raised when a broker operation is used incorrectly."""


class MTConsumerNotStarted(MTInvalidMessagingException):
    """Exception raised when a queue is bound before the connection is open.

    Notes:
        The connection, the channel and the exchanges are per-process, while
        the queues are per-agency and arrive one at a time. Binding before
        connecting is a programming error rather than a broker failure, so it
        says so instead of surfacing as an attribute error on ``None``.
    """
