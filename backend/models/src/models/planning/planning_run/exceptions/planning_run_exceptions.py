class MTInvalidPlanningRunException(Exception):
    """Exception raised when an invalid PlanningRun field is provided."""


class MTPlanningRunInvalidId(MTInvalidPlanningRunException):
    """Exception raised when an invalid identifier is provided."""


class MTPlanningRunInvalidStatus(MTInvalidPlanningRunException):
    """Exception raised when an invalid ``status`` value is provided."""


class MTPlanningRunInvalidPeriod(MTInvalidPlanningRunException):
    """Exception raised when an invalid planning period is provided."""


class MTPlanningRunInvalidCount(MTInvalidPlanningRunException):
    """Exception raised when an invalid count value is provided."""


class MTPlanningRunInvalidDate(MTInvalidPlanningRunException):
    """Exception raised when an invalid timestamp value is provided."""


class MTPlanningRunInvalidUnassigned(MTInvalidPlanningRunException):
    """Exception raised when an invalid unassigned-id list is provided."""


class MTPlanningRunInvalidError(MTInvalidPlanningRunException):
    """Exception raised when an invalid ``error_message`` value is provided."""
