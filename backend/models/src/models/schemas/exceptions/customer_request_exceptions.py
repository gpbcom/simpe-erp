class MTInvalidStatusUpdateRequestException(Exception):
    """Exception raised when a registration-status payload is invalid."""


class MTStatusUpdateRequestInvalidStatus(MTInvalidStatusUpdateRequestException):
    """Exception raised when the registration status is not a known one."""
