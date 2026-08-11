class MTInvoicingServiceException(Exception):
    """Exception raised when an e-invoicing integration cannot be worked with."""


class MTIntegrationCredentialsRefused(MTInvoicingServiceException):
    """Exception raised when a platform would not accept the credentials.

    Notes:
        Carries the connector's own message rather than a generic one, because
        that message is the actionable half: re-enter the key, or wait for the
        platform to come back.
    """


class MTIntegrationNotConfigured(MTInvoicingServiceException):
    """Exception raised when an agency has not connected the named platform."""


class MTNoActivePlatform(MTInvoicingServiceException):
    """Exception raised when a settled invoice has nowhere to be transmitted.

    Notes:
        The one transmission failure that is raised rather than recorded: it is
        not an attempt that went wrong but one that could not be made, and the
        answer is a screen telling somebody to connect a platform rather than a
        row to retry.
    """
