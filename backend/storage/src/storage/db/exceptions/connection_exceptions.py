class MTInvalidDatabaseConnectionException(Exception):
    """Exception raised when a database connection operation fails."""


class MTDatabaseNotConnected(MTInvalidDatabaseConnectionException):
    """Exception raised when the manager is used before ``connect()``."""


class MTDatabaseConnectionFailed(MTInvalidDatabaseConnectionException):
    """Exception raised when every connection attempt failed."""
