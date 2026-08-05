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
