class MTInvalidCertificationTypeUpdateRequestException(Exception):
    """Exception raised when a certification-catalogue edit is malformed."""


class MTCertificationTypeUpdateRequestInvalidLabel(
    MTInvalidCertificationTypeUpdateRequestException
):
    """Exception raised when the display label is empty."""


class MTCertificationTypeUpdateRequestInvalidDescription(
    MTInvalidCertificationTypeUpdateRequestException
):
    """Exception raised when the description is not text."""


class MTCertificationTypeUpdateRequestInvalidIsActive(
    MTInvalidCertificationTypeUpdateRequestException
):
    """Exception raised when the retirement flag is not a boolean."""
