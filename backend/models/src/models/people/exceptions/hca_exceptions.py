class MTInvalidHcaException(Exception):
    """Exception raised when an invalid Hca field is provided."""


class MTHcaInvalidId(MTInvalidHcaException):
    """Exception raised when an invalid ``id`` value is provided."""


class MTHcaInvalidFirstName(MTInvalidHcaException):
    """Exception raised when an invalid ``first_name`` value is provided."""


class MTHcaInvalidLastName(MTInvalidHcaException):
    """Exception raised when an invalid ``last_name`` value is provided."""


class MTHcaInvalidPhoneNumber(MTInvalidHcaException):
    """Exception raised when an invalid ``phone_number`` value is provided."""


class MTHcaInvalidEmail(MTInvalidHcaException):
    """Exception raised when an invalid ``email`` value is provided."""


class MTHcaInvalidAddress(MTInvalidHcaException):
    """Exception raised when an invalid ``address`` value is provided."""


class MTHcaInvalidContractType(MTInvalidHcaException):
    """Exception raised when an invalid ``contract_type`` value is provided."""


class MTHcaInvalidCertifications(MTInvalidHcaException):
    """Exception raised when an invalid ``certifications`` list is provided."""


class MTHcaInvalidDrivingLicense(MTInvalidHcaException):
    """Exception raised when an invalid ``driving_license`` value is provided."""


class MTHcaInvalidPhotoUrl(MTInvalidHcaException):
    """Exception raised when an invalid ``photo_url`` value is provided."""


class MTHcaInvalidAvailability(MTInvalidHcaException):
    """Exception raised when an invalid ``availability`` list is provided."""


class MTHcaInvalidDate(MTInvalidHcaException):
    """Exception raised when an invalid timestamp value is provided."""
