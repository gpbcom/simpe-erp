class MTInvalidHcaServiceException(Exception):
    """Exception raised when an assistant operation fails."""


class MTHcaNotFound(MTInvalidHcaServiceException):
    """Exception raised when the named assistant does not exist."""


class MTHcaHasAccount(MTInvalidHcaServiceException):
    """Exception raised when deleting an assistant an account still points at."""


class MTHcaForbidden(MTInvalidHcaServiceException):
    """Exception raised when a caller acts on an assistant who is not them.

    Notes:
        Row-level, not route-level. A route guard proves the caller is *an*
        assistant; only comparing the addressed assistant against their own
        record stops one booking another off work.
    """


class MTAvailabilitySlotNotFound(MTInvalidHcaServiceException):
    """Exception raised when the named absence does not belong to the assistant."""


class MTApplicationNotFound(MTInvalidHcaServiceException):
    """Exception raised when the named application does not exist."""


class MTApplicationForbidden(MTInvalidHcaServiceException):
    """Exception raised when a manager decides another company's application.

    Notes:
        Row-level, not route-level. A guard proves the caller is a manager; it
        cannot tell whose hiring queue the identifier in the path belongs to.
    """


class MTApplicationAlreadyDecided(MTInvalidHcaServiceException):
    """Exception raised when an application is decided twice.

    Notes:
        Approving twice would create a second assistant and a second account
        for one person; rejecting an approved one would strand the account the
        approval already created.
    """


class MTDuplicateApplication(MTInvalidHcaServiceException):
    """Exception raised when somebody applies twice to the same company."""
