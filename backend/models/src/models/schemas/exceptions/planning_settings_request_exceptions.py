class MTInvalidPlanningSettingsRequestException(Exception):
    """Exception raised when a planning-settings payload is invalid."""


class MTPlanningSettingsRequestInvalidRadius(MTInvalidPlanningSettingsRequestException):
    """Exception raised when the radius is not a usable distance."""


class MTPlanningSettingsRequestInvalidLunchBreak(
    MTInvalidPlanningSettingsRequestException
):
    """Exception raised when the lunch break is below the contractual floor."""
