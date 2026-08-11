class MTInvalidSkillTypeUpdateRequestException(Exception):
    """Exception raised when an invalid SkillTypeUpdateRequest is provided."""


class MTSkillTypeUpdateRequestInvalidLabel(MTInvalidSkillTypeUpdateRequestException):
    """Exception raised when an invalid ``label`` value is provided."""


class MTSkillTypeUpdateRequestInvalidDescription(
    MTInvalidSkillTypeUpdateRequestException
):
    """Exception raised when an invalid ``description`` value is provided."""


class MTSkillTypeUpdateRequestInvalidIsActive(MTInvalidSkillTypeUpdateRequestException):
    """Exception raised when an invalid ``is_active`` value is provided."""


class MTInvalidSkillCreateRequestException(Exception):
    """Exception raised when an invalid SkillCreateRequest is provided."""


class MTSkillCreateRequestInvalidName(MTInvalidSkillCreateRequestException):
    """Exception raised when an invalid ``name`` value is provided."""


class MTSkillCreateRequestInvalidCode(MTInvalidSkillCreateRequestException):
    """Exception raised when an invalid ``code`` value is provided."""


class MTSkillCreateRequestInvalidIssuer(MTInvalidSkillCreateRequestException):
    """Exception raised when an invalid ``issuer`` value is provided."""


class MTSkillCreateRequestInvalidDate(MTInvalidSkillCreateRequestException):
    """Exception raised when an invalid date value is provided."""
