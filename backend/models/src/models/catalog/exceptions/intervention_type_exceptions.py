class MTInvalidInterventionTypeException(Exception):
    """Exception raised when an invalid InterventionType field is provided."""


class MTInterventionTypeInvalidId(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``id`` value is provided."""


class MTInterventionTypeInvalidName(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``name`` value is provided."""


class MTInterventionTypeInvalidCode(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``code`` value is provided."""


class MTInterventionTypeInvalidDescription(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``description`` value is provided."""


class MTInterventionTypeInvalidServiceCategory(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``service_category`` is provided."""


class MTInterventionTypeInvalidHourlyRate(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``base_hourly_rate_ht`` is provided."""


class MTInterventionTypeInvalidIsActive(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``is_active`` value is provided."""


class MTInterventionTypeInvalidDate(MTInvalidInterventionTypeException):
    """Exception raised when an invalid timestamp value is provided."""
