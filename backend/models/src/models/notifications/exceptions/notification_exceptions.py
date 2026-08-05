class MTInvalidNotificationException(Exception):
    """Exception raised when an invalid Notification field is provided."""


class MTNotificationInvalidId(MTInvalidNotificationException):
    """Exception raised when an identifier is neither None nor a string."""


class MTNotificationInvalidRecipient(MTInvalidNotificationException):
    """Exception raised when a notification names no recipient.

    Notes:
        A notification without a recipient is one nobody will ever see. It is
        refused at construction rather than stored and quietly ignored, because
        the failure it hides — a quote waiting for a validation nobody is told
        about — looks exactly like nothing happening.
    """


class MTNotificationInvalidKind(MTInvalidNotificationException):
    """Exception raised when the kind is outside the enumeration."""


class MTNotificationInvalidTitle(MTInvalidNotificationException):
    """Exception raised when the title is not a non-empty string."""


class MTNotificationInvalidDate(MTInvalidNotificationException):
    """Exception raised when a timestamp is neither None nor datetime-like."""


class MTNotificationInvalidReadState(MTInvalidNotificationException):
    """Exception raised when the read flag is not a boolean."""
