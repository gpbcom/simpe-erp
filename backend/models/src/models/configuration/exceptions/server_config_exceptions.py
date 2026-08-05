class MTInvalidServerConfigException(Exception):
    """Exception raised when an invalid ServerConfig field is provided."""


class MTServerConfigInvalidHost(MTInvalidServerConfigException):
    """Exception raised when an invalid ``host`` value is provided."""


class MTServerConfigInvalidPort(MTInvalidServerConfigException):
    """Exception raised when an invalid ``port`` value is provided."""


class MTServerConfigInvalidCorsOrigins(MTInvalidServerConfigException):
    """Exception raised when an invalid ``cors_origins`` list is provided."""
