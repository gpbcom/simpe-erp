class MTInvalidCertificationTypeException(Exception):
    """Exception raised when an invalid CertificationType field is provided."""


class MTCertificationTypeInvalidId(MTInvalidCertificationTypeException):
    """Exception raised when an invalid ``id`` value is provided."""


class MTCertificationTypeInvalidCode(MTInvalidCertificationTypeException):
    """Exception raised when an invalid ``code`` value is provided.

    Notes:
        The code is what an assistant's qualification and an intervention
        type's requirement are matched on, so a malformed one would silently
        match nothing rather than fail.
    """


class MTCertificationTypeInvalidLabel(MTInvalidCertificationTypeException):
    """Exception raised when an invalid ``label`` value is provided."""


class MTCertificationTypeInvalidDescription(MTInvalidCertificationTypeException):
    """Exception raised when an invalid ``description`` value is provided."""


class MTCertificationTypeInvalidIsActive(MTInvalidCertificationTypeException):
    """Exception raised when an invalid ``is_active`` value is provided."""


class MTCertificationTypeInvalidDate(MTInvalidCertificationTypeException):
    """Exception raised when an invalid timestamp value is provided."""
