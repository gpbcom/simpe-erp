class MTInvalidDatabaseConfigException(Exception):
    """Exception raised when an invalid DatabaseConfig field is provided."""


class MTDatabaseConfigInvalidHost(MTInvalidDatabaseConfigException):
    """Exception raised when an invalid ``host`` value is provided."""


class MTDatabaseConfigInvalidPort(MTInvalidDatabaseConfigException):
    """Exception raised when an invalid ``port`` value is provided."""


class MTDatabaseConfigInvalidDatabase(MTInvalidDatabaseConfigException):
    """Exception raised when an invalid ``database`` value is provided."""


class MTDatabaseConfigInvalidUsername(MTInvalidDatabaseConfigException):
    """Exception raised when an invalid ``username`` value is provided."""


class MTDatabaseConfigInvalidPasswordEnv(MTInvalidDatabaseConfigException):
    """Exception raised when an invalid ``password_env`` value is provided."""


class MTDatabaseConfigInvalidPoolSize(MTInvalidDatabaseConfigException):
    """Exception raised when an invalid pool sizing value is provided."""


class MTDatabaseConfigMissingPassword(MTInvalidDatabaseConfigException):
    """Exception raised when the configured password env var is not set."""
