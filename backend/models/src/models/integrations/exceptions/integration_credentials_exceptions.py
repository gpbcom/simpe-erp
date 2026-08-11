class MTInvalidIntegrationCredentialsException(Exception):
    """Exception raised when an invalid IntegrationCredentials field is provided."""


class MTIntegrationCredentialsInvalidApiKey(MTInvalidIntegrationCredentialsException):
    """Exception raised when the API key is missing or is not a secret.

    Notes:
        The message deliberately never quotes the offending value. Every other
        validator in this codebase reports what it refused, which is what makes
        a 422 actionable — but here the refused value is the secret itself, and
        it would be written into the application log on the way past.
    """


class MTIntegrationCredentialsInvalidAccountId(
    MTInvalidIntegrationCredentialsException
):
    """Exception raised when the account reference is not usable text."""


class MTIntegrationCredentialsInvalidLegalEntityId(
    MTInvalidIntegrationCredentialsException
):
    """Exception raised when the legal-entity reference is not usable text."""


class MTIntegrationCredentialsInvalidBaseUrl(MTInvalidIntegrationCredentialsException):
    """Exception raised when the base URL is not an absolute HTTPS address.

    Notes:
        Plain HTTP is refused rather than upgraded. The value carries an API key
        on every request it is used for, and silently rewriting a deployment's
        configured address is how an operator comes to believe they are talking
        to a host they are not.
    """
