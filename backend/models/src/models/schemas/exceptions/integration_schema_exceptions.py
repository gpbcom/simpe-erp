class MTInvalidIntegrationSchemaException(Exception):
    """Exception raised when an invalid integration payload is provided."""


class MTEInvoicingIntegrationRequestInvalidField(
    MTInvalidIntegrationSchemaException
):
    """Exception raised when the enable payload is missing or malformed.

    Notes:
        The message never quotes the offending value. This payload carries an
        API key, and a 422 that repeats what it refused would write it into the
        application log on the way out.
    """


class MTIntegrationCardResponseInvalidProvider(
    MTInvalidIntegrationSchemaException
):
    """Exception raised when a gallery card names no supported platform."""
