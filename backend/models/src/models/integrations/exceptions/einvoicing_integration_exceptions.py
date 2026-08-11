class MTInvalidEInvoicingIntegrationException(Exception):
    """Exception raised when an invalid EInvoicingIntegration field is provided."""


class MTEInvoicingIntegrationInvalidId(MTInvalidEInvoicingIntegrationException):
    """Exception raised when the identifier is missing or empty."""


class MTEInvoicingIntegrationInvalidCompany(MTInvalidEInvoicingIntegrationException):
    """Exception raised when the owning agency is not identified.

    Notes:
        An integration with no agency would be readable by every tenant, and it
        holds the credentials of a platform account somebody pays for.
    """


class MTEInvoicingIntegrationInvalidProvider(MTInvalidEInvoicingIntegrationException):
    """Exception raised when the platform is missing or unknown."""


class MTEInvoicingIntegrationInvalidEnabled(MTInvalidEInvoicingIntegrationException):
    """Exception raised when the enabled flag is not a boolean."""


class MTEInvoicingIntegrationInvalidCiphertext(MTInvalidEInvoicingIntegrationException):
    """Exception raised when the stored credentials are missing or unreadable."""


class MTEInvoicingIntegrationInvalidHint(MTInvalidEInvoicingIntegrationException):
    """Exception raised when the credential hint is not a short masked tail.

    Notes:
        Bounded rather than merely typed. The hint exists so a screen can say
        *something is configured* without being able to say what, and a hint
        long enough to hold the whole key would defeat the only reason the
        ciphertext is kept out of the payload.
    """


class MTEInvoicingIntegrationInvalidDate(MTInvalidEInvoicingIntegrationException):
    """Exception raised when an invalid timestamp value is provided."""


class MTEInvoicingIntegrationInvalidError(MTInvalidEInvoicingIntegrationException):
    """Exception raised when the recorded check failure is not usable text."""
