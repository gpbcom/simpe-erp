class MTInvalidGeocodingConfigException(Exception):
    """Exception raised when an invalid GeocodingConfig field is provided."""


class MTGeocodingConfigInvalidBaseUrl(MTInvalidGeocodingConfigException):
    """Exception raised when an invalid ``base_url`` value is provided."""


class MTGeocodingConfigInvalidUserAgent(MTInvalidGeocodingConfigException):
    """Exception raised when an invalid ``user_agent`` value is provided."""


class MTGeocodingConfigInvalidTimeout(MTInvalidGeocodingConfigException):
    """Exception raised when an invalid ``timeout_seconds`` is provided."""


class MTGeocodingConfigInvalidCountryCodes(MTInvalidGeocodingConfigException):
    """Exception raised when an invalid ``country_codes`` list is provided."""
