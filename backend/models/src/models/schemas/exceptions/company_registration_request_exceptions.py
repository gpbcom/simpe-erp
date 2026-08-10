class MTInvalidCompanyRegistrationRequestException(Exception):
    """Exception raised when an invalid CompanyRegistrationRequest is provided."""


class MTCompanyRegistrationRequestInvalidCompanyName(
    MTInvalidCompanyRegistrationRequestException
):
    """Exception raised when an invalid ``company_name`` value is provided."""


class MTCompanyRegistrationRequestInvalidRegistrationNumber(
    MTInvalidCompanyRegistrationRequestException
):
    """Exception raised when an invalid ``registration_number`` is provided."""


class MTCompanyRegistrationRequestInvalidEmail(
    MTInvalidCompanyRegistrationRequestException
):
    """Exception raised when an invalid ``email`` value is provided."""


class MTCompanyRegistrationRequestInvalidFullName(
    MTInvalidCompanyRegistrationRequestException
):
    """Exception raised when an invalid ``full_name`` value is provided."""


class MTCompanyRegistrationRequestInvalidPassword(
    MTInvalidCompanyRegistrationRequestException
):
    """Exception raised when an invalid ``password`` value is provided."""


class MTInvalidCompanyProfileUpdateRequestException(Exception):
    """Exception raised when an agency-details payload is invalid."""


class MTCompanyProfileUpdateRequestInvalidName(
    MTInvalidCompanyProfileUpdateRequestException
):
    """Exception raised when the trading name is empty."""


class MTCompanyProfileUpdateRequestInvalidRegistrationNumber(
    MTInvalidCompanyProfileUpdateRequestException
):
    """Exception raised when the registration number is malformed."""


class MTCompanyProfileUpdateRequestInvalidIban(
    MTInvalidCompanyProfileUpdateRequestException
):
    """Exception raised when the submitted IBAN is not a string."""


class MTCompanyProfileUpdateRequestInvalidBic(
    MTInvalidCompanyProfileUpdateRequestException
):
    """Exception raised when the submitted BIC is not a string."""
