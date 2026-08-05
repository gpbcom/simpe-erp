class MTInvalidHcaApplicationException(Exception):
    """Exception raised when an assistant's application is invalid."""


class MTHcaApplicationInvalidId(MTInvalidHcaApplicationException):
    """Exception raised when an identifier is not a non-empty string."""


class MTHcaApplicationInvalidName(MTInvalidHcaApplicationException):
    """Exception raised when a name is empty."""


class MTHcaApplicationInvalidEmail(MTInvalidHcaApplicationException):
    """Exception raised when the address is not an email address."""


class MTHcaApplicationInvalidStatus(MTInvalidHcaApplicationException):
    """Exception raised when the status is not a known one."""


class MTHcaApplicationInvalidCompany(MTInvalidHcaApplicationException):
    """Exception raised when no company was chosen to apply to."""


class MTHcaApplicationInvalidPasswordHash(MTInvalidHcaApplicationException):
    """Exception raised when the stored credential is not a hash."""


class MTHcaApplicationInvalidDecision(MTInvalidHcaApplicationException):
    """Exception raised when a decided application has no decision recorded."""


class MTHcaApplicationInvalidDate(MTInvalidHcaApplicationException):
    """Exception raised when a timestamp is not a datetime."""
