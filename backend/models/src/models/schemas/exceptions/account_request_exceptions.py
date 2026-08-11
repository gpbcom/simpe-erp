class MTInvalidHcaApplicationRequestException(Exception):
    """Exception raised when a self-registration payload is invalid."""


class MTHcaApplicationRequestInvalidCompany(MTInvalidHcaApplicationRequestException):
    """Exception raised when no company was chosen."""


class MTHcaApplicationRequestInvalidPassword(MTInvalidHcaApplicationRequestException):
    """Exception raised when the chosen password is too weak."""


class MTHcaApplicationRequestInvalidName(MTInvalidHcaApplicationRequestException):
    """Exception raised when a name is empty."""


class MTInvalidStaffAccountRequestException(Exception):
    """Exception raised when a staff-created account payload is invalid."""


class MTStaffAccountRequestInvalidHcaId(MTInvalidStaffAccountRequestException):
    """Exception raised when the assistant record is not named."""


class MTStaffAccountRequestInvalidFullName(MTInvalidStaffAccountRequestException):
    """Exception raised when the display name is empty."""


class MTInvalidCustomerAccountRequestException(Exception):
    """Exception raised when a customer portal-account payload is invalid."""


class MTCustomerAccountRequestInvalidFullName(MTInvalidCustomerAccountRequestException):
    """Exception raised when the display name is empty."""


class MTInvalidPasswordChangeRequestException(Exception):
    """Exception raised when a password-change payload is invalid."""


class MTPasswordChangeRequestInvalidCurrent(MTInvalidPasswordChangeRequestException):
    """Exception raised when the current password is missing."""


class MTPasswordChangeRequestInvalidNew(MTInvalidPasswordChangeRequestException):
    """Exception raised when the new password is too weak."""


class MTInvalidApplicationDecisionRequestException(Exception):
    """Exception raised when an approval or rejection payload is invalid."""


class MTApplicationDecisionRequestInvalidContractType(
    MTInvalidApplicationDecisionRequestException
):
    """Exception raised when the contract type is not a known one."""


class MTInvalidAccountUpdateRequestException(Exception):
    """Exception raised when a self-service account payload is invalid."""


class MTAccountUpdateRequestInvalidFullName(MTInvalidAccountUpdateRequestException):
    """Exception raised when the display name is empty."""


class MTAccountUpdateRequestInvalidEmail(MTInvalidAccountUpdateRequestException):
    """Exception raised when the sign-in address is empty."""


class MTInvalidQuoteInterruptionRequestException(Exception):
    """Exception raised when an interruption payload is invalid."""


class MTQuoteInterruptionRequestInvalidDay(MTInvalidQuoteInterruptionRequestException):
    """Exception raised when the last day is missing or unreadable."""


class MTAccountUpdateRequestInvalidLanguage(MTInvalidAccountUpdateRequestException):
    """Exception raised when the language is not one the application speaks."""
