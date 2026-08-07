class MTInvalidAppConfigException(Exception):
    """Exception raised when an invalid AppConfig field is provided."""


class MTAppConfigInvalidServer(MTInvalidAppConfigException):
    """Exception raised when an invalid ``server`` section is provided."""


class MTAppConfigInvalidDatabase(MTInvalidAppConfigException):
    """Exception raised when an invalid ``database`` section is provided."""


class MTAppConfigInvalidAuth(MTInvalidAppConfigException):
    """Exception raised when an invalid ``auth`` section is provided."""


class MTAppConfigInvalidPricing(MTInvalidAppConfigException):
    """Exception raised when an invalid ``pricing`` section is provided."""


class MTAppConfigInvalidPlanning(MTInvalidAppConfigException):
    """Exception raised when an invalid ``planning`` section is provided."""


class MTAppConfigInvalidGeocoding(MTInvalidAppConfigException):
    """Exception raised when an invalid ``geocoding`` section is provided."""


class MTAppConfigInvalidObservability(MTInvalidAppConfigException):
    """Exception raised when the ``observability`` section is not a mapping."""


class MTAppConfigInvalidS3(MTInvalidAppConfigException):
    """Exception raised when an invalid ``s3`` section is provided."""


class MTAppConfigNotFound(MTInvalidAppConfigException):
    """Exception raised when the configuration file cannot be located."""


class MTAppConfigUnreadable(MTInvalidAppConfigException):
    """Exception raised when the configuration file cannot be parsed."""


class MTAppConfigInvalidRabbitMq(MTInvalidAppConfigException):
    """Exception raised when the rabbitmq section is not a mapping."""
