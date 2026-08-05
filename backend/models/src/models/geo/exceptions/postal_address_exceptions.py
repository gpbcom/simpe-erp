class MTInvalidPostalAddressException(Exception):
    """Exception raised when an invalid PostalAddress field is provided."""


class MTPostalAddressInvalidStreet(MTInvalidPostalAddressException):
    """Exception raised when an invalid ``street`` value is provided."""


class MTPostalAddressInvalidPostalCode(MTInvalidPostalAddressException):
    """Exception raised when an invalid ``postal_code`` value is provided."""


class MTPostalAddressInvalidCity(MTInvalidPostalAddressException):
    """Exception raised when an invalid ``city`` value is provided."""


class MTPostalAddressInvalidCountry(MTInvalidPostalAddressException):
    """Exception raised when an invalid ``country`` value is provided."""


class MTPostalAddressInvalidLatitude(MTInvalidPostalAddressException):
    """Exception raised when an invalid ``latitude`` value is provided."""


class MTPostalAddressInvalidLongitude(MTInvalidPostalAddressException):
    """Exception raised when an invalid ``longitude`` value is provided."""


class MTPostalAddressInvalidGeocodingError(MTInvalidPostalAddressException):
    """Exception raised when an unknown ``geocoding_error`` code is provided."""


class MTPostalAddressGeocodingFailed(MTInvalidPostalAddressException):
    """Exception raised when the geocoding service cannot be reached."""


class MTPostalAddressNotFound(MTInvalidPostalAddressException):
    """Exception raised when the geocoding service returns no candidate."""


class MTPostalAddressInvalidResponse(MTInvalidPostalAddressException):
    """Exception raised when the geocoding response cannot be parsed."""
