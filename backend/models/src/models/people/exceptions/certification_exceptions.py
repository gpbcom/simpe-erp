class MTInvalidCertificationException(Exception):
    """Exception raised when an invalid Certification field is provided."""


class MTCertificationInvalidName(MTInvalidCertificationException):
    """Exception raised when an invalid ``name`` value is provided."""


class MTCertificationInvalidIssuer(MTInvalidCertificationException):
    """Exception raised when an invalid ``issuer`` value is provided."""


class MTCertificationInvalidObtainedOn(MTInvalidCertificationException):
    """Exception raised when an invalid ``obtained_on`` value is provided."""


class MTCertificationInvalidExpiresOn(MTInvalidCertificationException):
    """Exception raised when an invalid ``expires_on`` value is provided."""
