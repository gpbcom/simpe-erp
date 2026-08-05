class MTInvalidRabbitMqConfigException(Exception):
    """Exception raised when the broker configuration is malformed."""


class MTRabbitMqConfigInvalidHost(MTInvalidRabbitMqConfigException):
    """Exception raised when the broker host is not a non-empty string."""


class MTRabbitMqConfigInvalidPort(MTInvalidRabbitMqConfigException):
    """Exception raised when a numeric broker setting is out of range."""


class MTRabbitMqConfigInvalidExchange(MTInvalidRabbitMqConfigException):
    """Exception raised when an exchange, vhost or username is empty."""


class MTRabbitMqConfigInvalidEnvName(MTInvalidRabbitMqConfigException):
    """Exception raised when the password variable name is empty."""


class MTRabbitMqConfigInvalidTimeout(MTInvalidRabbitMqConfigException):
    """Exception raised when the publish timeout is not a positive number."""
