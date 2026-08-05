class MTInvalidHcaResponseException(Exception):
    """Exception raised when an invalid HcaResponse field is provided."""


class MTHcaResponseInvalidId(MTInvalidHcaResponseException):
    """Exception raised when an invalid ``id`` value is provided."""


class MTHcaResponseInvalidName(MTInvalidHcaResponseException):
    """Exception raised when an invalid name value is provided."""


class MTHcaResponseInvalidContractType(MTInvalidHcaResponseException):
    """Exception raised when an invalid ``contract_type`` value is provided."""


class MTHcaResponseInvalidDate(MTInvalidHcaResponseException):
    """Exception raised when an invalid timestamp value is provided."""
