class MTInvalidHealthResponseException(Exception):
    """Exception raised when an invalid HealthResponse field is provided."""


class MTHealthResponseInvalidStatus(MTInvalidHealthResponseException):
    """Exception raised when an invalid ``status`` value is provided."""


class MTInvalidReadinessResponseException(Exception):
    """Exception raised when an invalid ReadinessResponse field is provided."""


class MTReadinessResponseInvalidStatus(MTInvalidReadinessResponseException):
    """Exception raised when an invalid ``status`` value is provided."""


class MTReadinessResponseInvalidDatabase(MTInvalidReadinessResponseException):
    """Exception raised when an invalid ``database`` value is provided."""
