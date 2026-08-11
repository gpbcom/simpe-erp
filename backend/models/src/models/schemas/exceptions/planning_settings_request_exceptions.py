class MTInvalidPlanningSettingsRequestException(Exception):
    """Exception raised when a planning-settings payload is invalid."""


class MTPlanningSettingsRequestInvalidRadius(MTInvalidPlanningSettingsRequestException):
    """Exception raised when the radius is not a usable distance."""


class MTPlanningSettingsRequestInvalidLunchBreak(
    MTInvalidPlanningSettingsRequestException
):
    """Exception raised when the lunch break is below the contractual floor."""


class MTPlanningSettingsRequestInvalidDayStart(
    MTInvalidPlanningSettingsRequestException
):
    """Exception raised when the day does not start at a minute of day."""


class MTPlanningSettingsRequestInvalidDayEnd(MTInvalidPlanningSettingsRequestException):
    """Exception raised when the day does not end after it starts."""


class MTPlanningSettingsRequestInvalidLunchWindow(
    MTInvalidPlanningSettingsRequestException
):
    """Exception raised when the lunch window cannot hold the break."""
