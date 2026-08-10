class MTInvalidCompanyServiceException(Exception):
    """Exception raised when a company operation fails."""


class MTCompanyNotFound(MTInvalidCompanyServiceException):
    """Exception raised when the named company does not exist."""


class MTCompanyNameTaken(MTInvalidCompanyServiceException):
    """Exception raised when another company already trades under the name."""


class MTCompanyNotAcceptingApplications(MTInvalidCompanyServiceException):
    """Exception raised when a company has closed its applications.

    Notes:
        Deliberately distinct from "no such company". An applicant who is told
        the agency does not exist will go looking for a typo; one told it is
        not currently hiring will try another.
    """


class MTCompanyRegistrationDisabled(MTInvalidCompanyServiceException):
    """Exception raised when founding an agency is not enabled.

    Notes:
        Answered as a 404 rather than a 403. A deployment that has not opted in
        should look like one that has no such route at all: a 403 confirms the
        feature exists and is merely switched off, which is an invitation to
        keep checking whether it has been switched on.
    """


class MTCompanyLogoStorageUnavailable(MTInvalidCompanyServiceException):
    """Exception raised when a logo operation runs with no object store.

    Notes:
        Answered as a 503, because it describes the deployment rather than the
        request: the same call will work once an object store is configured,
        and nothing the caller can change about the payload will help.

        Raised rather than skipped. Somebody who uploaded an image and got a
        2xx back would reasonably believe it was kept.
    """


class MTCompanyNotEmpty(MTInvalidCompanyServiceException):
    """Exception raised when an agency still has people attached to it.

    Notes:
        Every account and every assistant names the agency they belong to, and
        that link is required. Removing the agency underneath them would leave
        rows nothing can rebuild, so the refusal names what is still attached.
    """
