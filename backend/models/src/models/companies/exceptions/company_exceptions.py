class MTInvalidCompanyException(Exception):
    """Exception raised when a company is invalid."""


class MTCompanyInvalidId(MTInvalidCompanyException):
    """Exception raised when the identifier is not a non-empty string."""


class MTCompanyInvalidName(MTInvalidCompanyException):
    """Exception raised when the trading name is empty or too long."""


class MTCompanyInvalidRegistrationNumber(MTInvalidCompanyException):
    """Exception raised when the registration number is malformed."""


class MTCompanyInvalidEmail(MTInvalidCompanyException):
    """Exception raised when the contact address is not an email address."""


class MTCompanyInvalidIsAcceptingApplications(MTInvalidCompanyException):
    """Exception raised when the open-to-applications flag is not a boolean."""


class MTCompanyInvalidDate(MTInvalidCompanyException):
    """Exception raised when a timestamp is not a datetime."""
