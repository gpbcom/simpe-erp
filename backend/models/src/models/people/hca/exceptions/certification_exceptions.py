class MTInvalidCertificationException(Exception):
    """Exception raised when an invalid Certification field is provided."""


class MTCertificationInvalidName(MTInvalidCertificationException):
    """Exception raised when an invalid ``name`` value is provided."""


class MTCertificationInvalidCode(MTInvalidCertificationException):
    """Exception raised when an invalid ``code`` value is provided.

    Notes:
        The code is what the planner matches a requirement against. A
        malformed one would match nothing and quietly leave its holder
        unqualified, so it is refused rather than stored.
    """


class MTCertificationInvalidIssuer(MTInvalidCertificationException):
    """Exception raised when an invalid ``issuer`` value is provided."""


class MTCertificationInvalidObtainedOn(MTInvalidCertificationException):
    """Exception raised when an invalid ``obtained_on`` value is provided."""


class MTCertificationInvalidExpiresOn(MTInvalidCertificationException):
    """Exception raised when an invalid ``expires_on`` value is provided."""
