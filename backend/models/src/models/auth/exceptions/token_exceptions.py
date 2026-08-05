class MTInvalidAccessTokenException(Exception):
    """Exception raised when an invalid AccessToken field is provided."""


class MTAccessTokenInvalidAccessToken(MTInvalidAccessTokenException):
    """Exception raised when an invalid ``access_token`` value is provided."""


class MTAccessTokenInvalidTokenType(MTInvalidAccessTokenException):
    """Exception raised when an invalid ``token_type`` value is provided."""


class MTAccessTokenInvalidExpiresIn(MTInvalidAccessTokenException):
    """Exception raised when an invalid ``expires_in`` value is provided."""
