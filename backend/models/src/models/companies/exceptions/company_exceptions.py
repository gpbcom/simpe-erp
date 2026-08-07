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


class MTCompanyInvalidLegalForm(MTInvalidCompanyException):
    """Exception raised when the legal form is not a usable label.

    Notes:
        Free text rather than an enumeration, and refused only for being
        unusable. French home care is delivered by SARLs, SAS, associations,
        CCAS, mutuelles and sole traders alike; a closed list would lock out a
        provider whose form nobody thought of, on a field that only ever gets
        printed.
    """


class MTCompanyInvalidShareCapital(MTInvalidCompanyException):
    """Exception raised when the share capital is not a positive amount."""


class MTCompanyInvalidRcsNumber(MTInvalidCompanyException):
    """Exception raised when the RCS entry is not a usable label."""


class MTCompanyInvalidVatNumber(MTInvalidCompanyException):
    """Exception raised when the intra-community VAT number is malformed."""


class MTCompanyInvalidPhoneNumber(MTInvalidCompanyException):
    """Exception raised when the contact telephone number is not usable."""
