class MTInvalidSkillTypeException(Exception):
    """Exception raised when an invalid SkillType field is provided."""


class MTSkillTypeInvalidId(MTInvalidSkillTypeException):
    """Exception raised when an invalid ``id`` value is provided."""


class MTSkillTypeInvalidCode(MTInvalidSkillTypeException):
    """Exception raised when an invalid ``code`` value is provided.

    Notes:
        The code is what an assistant's declared skill and an intervention
        type's requirement are matched on, so a malformed one would silently
        match nothing rather than fail.
    """


class MTSkillTypeInvalidLabel(MTInvalidSkillTypeException):
    """Exception raised when an invalid ``label`` value is provided."""


class MTSkillTypeInvalidDescription(MTInvalidSkillTypeException):
    """Exception raised when an invalid ``description`` value is provided."""


class MTSkillTypeInvalidIsActive(MTInvalidSkillTypeException):
    """Exception raised when an invalid ``is_active`` value is provided."""


class MTSkillTypeInvalidDate(MTInvalidSkillTypeException):
    """Exception raised when an invalid timestamp value is provided."""
