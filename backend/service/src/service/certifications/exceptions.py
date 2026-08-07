class MTInvalidCertificationCatalogException(Exception):
    """Exception raised when a certification-catalogue operation fails."""


class MTCertificationTypeNotFound(MTInvalidCertificationCatalogException):
    """Exception raised when the named certification type does not exist."""


class MTCertificationTypeAlreadyExists(MTInvalidCertificationCatalogException):
    """Exception raised when the code is already used by another entry."""


class MTCertificationTypeUnknownCode(MTInvalidCertificationCatalogException):
    """Exception raised when a requirement names a code the catalogue lacks.

    Notes:
        Raised on the way in, when a service or a quote line is saved, rather
        than left to the planner. A requirement naming a code nobody can hold
        fails every planning run it touches, with a message that reads as a
        staffing problem — "no assistant holds XYZ" is true and useless when
        XYZ was a typo.
    """


class MTCertificationTypeInUse(MTInvalidCertificationCatalogException):
    """Exception raised when deleting an entry something still refers to.

    Notes:
        No foreign key protects the references, so this check is what stands in
        for one. Retiring the entry is offered instead: it stops the code being
        chosen again while leaving every stored qualification that names it
        still resolvable.
    """
