class MTInvalidRegisterRequestException(Exception):
    """Exception raised when an invalid RegisterRequest field is provided."""


class MTRegisterRequestInvalidEmail(MTInvalidRegisterRequestException):
    """Exception raised when an invalid ``email`` value is provided."""


class MTRegisterRequestInvalidFullName(MTInvalidRegisterRequestException):
    """Exception raised when an invalid ``full_name`` value is provided."""


class MTRegisterRequestInvalidPassword(MTInvalidRegisterRequestException):
    """Exception raised when an invalid ``password`` value is provided."""


class MTRegisterRequestInvalidRole(MTInvalidRegisterRequestException):
    """Exception raised when an invalid ``role`` value is provided."""


class MTRegisterRequestInvalidHcaId(MTInvalidRegisterRequestException):
    """Exception raised when an invalid ``hca_id`` value is provided."""


class MTInvalidLoginRequestException(Exception):
    """Exception raised when an invalid LoginRequest field is provided."""


class MTLoginRequestInvalidEmail(MTInvalidLoginRequestException):
    """Exception raised when an invalid ``email`` value is provided."""


class MTLoginRequestInvalidPassword(MTInvalidLoginRequestException):
    """Exception raised when an invalid ``password`` value is provided."""


class MTInvalidRoleUpdateRequestException(Exception):
    """Exception raised when an invalid RoleUpdateRequest field is provided."""


class MTRoleUpdateRequestInvalidRole(MTInvalidRoleUpdateRequestException):
    """Exception raised when an invalid ``role`` value is provided."""


class MTInvalidActiveUpdateRequestException(Exception):
    """Exception raised when an invalid ActiveUpdateRequest field is given."""


class MTActiveUpdateRequestInvalidIsActive(MTInvalidActiveUpdateRequestException):
    """Exception raised when an invalid ``is_active`` value is provided."""
