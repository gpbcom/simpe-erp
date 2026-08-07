# First-party imports
from models.base.exceptions import MTInvalidPersonException


class MTInvalidHcaApplicationException(MTInvalidPersonException):
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


class MTHcaApplicationInvalidPhoneNumber(MTInvalidHcaApplicationException):
    """Exception raised when the telephone number is not a non-empty string.

    Notes:
        Added when the model was rebased on
        :class:`~models.people.person.Person`. The rule was always there — a
        missing number was refused by the ``PhoneNumber`` type — but it
        surfaced as a bare Pydantic error rather than as this package's own
        exception, so the API answered it through the generic validation
        handler instead of the application one.
    """


class MTHcaApplicationInvalidAddress(MTInvalidHcaApplicationException):
    """Exception raised when the address is neither an address nor a mapping.

    Notes:
        Added for the same reason as
        :class:`MTHcaApplicationInvalidPhoneNumber`.
    """
