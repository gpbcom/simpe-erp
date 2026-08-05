class MTInvalidEmailException(Exception):
    """Exception raised when an outbound email operation fails."""


class MTEmailNotConfigured(MTInvalidEmailException):
    """Exception raised when outbound email is disabled or has no credentials."""


class MTEmailDeliveryFailed(MTInvalidEmailException):
    """Exception raised when the SMTP conversation fails."""


class MTEmailNoRecipient(MTInvalidEmailException):
    """Exception raised when the intended recipient has no email address."""
