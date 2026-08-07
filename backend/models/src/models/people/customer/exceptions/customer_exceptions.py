# First-party imports
from models.base.exceptions import MTInvalidPersonException


class MTInvalidCustomerException(MTInvalidPersonException):
    """Exception raised when an invalid Customer field is provided."""


class MTCustomerInvalidId(MTInvalidCustomerException):
    """Exception raised when an invalid ``id`` value is provided."""


class MTCustomerInvalidFirstName(MTInvalidCustomerException):
    """Exception raised when an invalid ``first_name`` value is provided."""


class MTCustomerInvalidLastName(MTInvalidCustomerException):
    """Exception raised when an invalid ``last_name`` value is provided."""


class MTCustomerInvalidPhoneNumber(MTInvalidCustomerException):
    """Exception raised when an invalid ``phone_number`` value is provided."""


class MTCustomerInvalidEmail(MTInvalidCustomerException):
    """Exception raised when an invalid ``email`` value is provided."""


class MTCustomerInvalidAddress(MTInvalidCustomerException):
    """Exception raised when an invalid ``address`` value is provided."""


class MTCustomerInvalidRegistrationStatus(MTInvalidCustomerException):
    """Exception raised when an invalid ``registration_status`` is provided."""


class MTCustomerInvalidDate(MTInvalidCustomerException):
    """Exception raised when an invalid timestamp value is provided."""
