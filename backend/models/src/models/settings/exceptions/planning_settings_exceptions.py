class MTInvalidPlanningSettingsException(Exception):
    """Exception raised when the planning settings are invalid."""


class MTPlanningSettingsInvalidId(MTInvalidPlanningSettingsException):
    """Exception raised when the identifier is not a non-empty string."""


class MTPlanningSettingsInvalidRadius(MTInvalidPlanningSettingsException):
    """Exception raised when the intervention radius is not a usable distance."""


class MTPlanningSettingsInvalidLunchBreak(MTInvalidPlanningSettingsException):
    """Exception raised when the lunch break is shorter than the legal floor."""


class MTPlanningSettingsInvalidUpdatedBy(MTInvalidPlanningSettingsException):
    """Exception raised when the editing account is not identified."""


class MTPlanningSettingsInvalidDate(MTInvalidPlanningSettingsException):
    """Exception raised when a timestamp is not a datetime."""
