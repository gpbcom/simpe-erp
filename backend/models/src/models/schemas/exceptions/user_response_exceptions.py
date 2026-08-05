class MTInvalidUserResponseException(Exception):
    """Exception raised when an invalid UserResponse field is provided."""


class MTUserResponseInvalidId(MTInvalidUserResponseException):
    """Exception raised when an invalid ``id`` value is provided."""


class MTUserResponseInvalidEmail(MTInvalidUserResponseException):
    """Exception raised when an invalid ``email`` value is provided."""


class MTUserResponseInvalidFullName(MTInvalidUserResponseException):
    """Exception raised when an invalid ``full_name`` value is provided."""


class MTUserResponseInvalidRole(MTInvalidUserResponseException):
    """Exception raised when an invalid ``role`` value is provided."""


class MTUserResponseInvalidIsActive(MTInvalidUserResponseException):
    """Exception raised when an invalid ``is_active`` value is provided."""


class MTUserResponseInvalidHcaId(MTInvalidUserResponseException):
    """Exception raised when an invalid ``hca_id`` value is provided."""


class MTUserResponseInvalidDate(MTInvalidUserResponseException):
    """Exception raised when an invalid timestamp value is provided."""
