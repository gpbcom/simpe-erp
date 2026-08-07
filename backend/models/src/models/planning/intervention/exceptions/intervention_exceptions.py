class MTInvalidInterventionException(Exception):
    """Exception raised when an invalid Intervention field is provided."""


class MTInterventionInvalidId(MTInvalidInterventionException):
    """Exception raised when an invalid identifier is provided."""


class MTInterventionInvalidName(MTInvalidInterventionException):
    """Exception raised when an invalid ``name`` value is provided."""


class MTInterventionInvalidDay(MTInvalidInterventionException):
    """Exception raised when an invalid ``day`` value is provided."""


class MTInterventionInvalidTime(MTInvalidInterventionException):
    """Exception raised when an invalid start or end time is provided."""


class MTInterventionInvalidStatus(MTInvalidInterventionException):
    """Exception raised when an invalid ``status`` value is provided."""


class MTInterventionInvalidAddress(MTInvalidInterventionException):
    """Exception raised when an invalid ``address`` value is provided."""
