class MTInvalidGeoPointException(Exception):
    """Exception raised when an invalid GeoPoint field is provided."""


class MTGeoPointInvalidLatitude(MTInvalidGeoPointException):
    """Exception raised when an invalid ``latitude`` value is provided."""


class MTGeoPointInvalidLongitude(MTInvalidGeoPointException):
    """Exception raised when an invalid ``longitude`` value is provided."""
