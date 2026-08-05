class MTInvalidUserException(Exception):
    """Exception raised when an invalid User field is provided."""


class MTUserInvalidId(MTInvalidUserException):
    """Exception raised when an invalid ``id`` value is provided."""


class MTUserInvalidEmail(MTInvalidUserException):
    """Exception raised when an invalid ``email`` value is provided."""


class MTUserInvalidHashedPassword(MTInvalidUserException):
    """Exception raised when an invalid ``hashed_password`` value is provided."""


class MTUserInvalidRole(MTInvalidUserException):
    """Exception raised when an invalid ``role`` value is provided."""


class MTUserInvalidHcaId(MTInvalidUserException):
    """Exception raised when an invalid ``hca_id`` value is provided."""


class MTUserInvalidFullName(MTInvalidUserException):
    """Exception raised when an invalid ``full_name`` value is provided."""


class MTUserInvalidDate(MTInvalidUserException):
    """Exception raised when an invalid timestamp value is provided."""


class MTUserRoleHcaRequiresHcaId(MTInvalidUserException):
    """Exception raised when an HCA account is not linked to an HCA record."""


class MTUserInvalidMustChangePassword(MTInvalidUserException):
    """Exception raised when the forced-change flag is not a boolean."""


class MTUserInvalidAccountOrigin(MTInvalidUserException):
    """Exception raised when the account origin is not a known one."""


class MTUserInvalidCompanyId(MTInvalidUserException):
    """Exception raised when the company identifier is not a string."""


class MTUserStaffAccountNeedsChange(MTInvalidUserException):
    """Exception raised when a staff-created account waives its password change.

    Notes:
        An account created by an administrator starts with a password its owner
        has never seen chosen. Building one that is not required to change it
        would leave a credential a second person knows, which is the whole
        thing the mandatory change exists to end.
    """
