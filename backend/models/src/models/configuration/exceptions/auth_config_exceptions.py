class MTInvalidAuthConfigException(Exception):
    """Exception raised when an invalid AuthConfig field is provided."""


class MTAuthConfigInvalidJwtSecretEnv(MTInvalidAuthConfigException):
    """Exception raised when an invalid ``jwt_secret_env`` value is provided."""


class MTAuthConfigInvalidJwtAlgorithm(MTInvalidAuthConfigException):
    """Exception raised when an unsupported ``jwt_algorithm`` is provided."""


class MTAuthConfigInvalidTokenExpiry(MTInvalidAuthConfigException):
    """Exception raised when an invalid ``access_token_expire_minutes`` is given."""


class MTAuthConfigMissingSecret(MTInvalidAuthConfigException):
    """Exception raised when the configured JWT secret env var is not set."""
