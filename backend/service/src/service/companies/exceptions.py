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
