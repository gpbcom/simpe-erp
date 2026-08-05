class MTInvalidTemporaryCredentialsResponseException(Exception):
    """Exception raised when a temporary-credentials response is invalid."""


class MTTemporaryCredentialsResponseInvalidPassword(
    MTInvalidTemporaryCredentialsResponseException
):
    """Exception raised when the temporary password is empty."""


class MTTemporaryCredentialsResponseInvalidEmail(
    MTInvalidTemporaryCredentialsResponseException
):
    """Exception raised when the sign-in address is empty."""
