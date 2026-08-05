class MTInvalidEmploymentUpdateRequestException(Exception):
    """Exception raised when an employment-change payload is invalid."""


class MTEmploymentUpdateRequestInvalidContractType(
    MTInvalidEmploymentUpdateRequestException
):
    """Exception raised when the contract type is not a known one."""


class MTEmploymentUpdateRequestInvalidCertifications(
    MTInvalidEmploymentUpdateRequestException
):
    """Exception raised when the certifications are not a list."""


class MTInvalidHcaProfileUpdateRequestException(Exception):
    """Exception raised when an assistant's own profile edit is malformed."""


class MTHcaProfileUpdateRequestInvalidName(MTInvalidHcaProfileUpdateRequestException):
    """Exception raised when a name part is not a non-empty string."""


class MTHcaProfileUpdateRequestInvalidAddress(
    MTInvalidHcaProfileUpdateRequestException
):
    """Exception raised when the address is neither an address nor a mapping."""
