class MTInvalidPlanningConfigException(Exception):
    """Exception raised when an invalid PlanningConfig field is provided."""


class MTPlanningConfigInvalidDayStart(MTInvalidPlanningConfigException):
    """Exception raised when an invalid ``day_start_minute`` is provided."""


class MTPlanningConfigInvalidDayEnd(MTInvalidPlanningConfigException):
    """Exception raised when an invalid ``day_end_minute`` is provided."""


class MTPlanningConfigInvalidLunchBreak(MTInvalidPlanningConfigException):
    """Exception raised when an invalid ``lunch_break_minutes`` is provided."""


class MTPlanningConfigInvalidLunchWindow(MTInvalidPlanningConfigException):
    """Exception raised when an invalid lunch window bound is provided."""


class MTPlanningConfigInvalidSpeed(MTInvalidPlanningConfigException):
    """Exception raised when an invalid average travel speed is provided."""


class MTPlanningConfigInvalidSolverTimeLimit(MTInvalidPlanningConfigException):
    """Exception raised when an invalid ``solver_time_limit_seconds`` is provided."""


class MTPlanningConfigInvalidPenalty(MTInvalidPlanningConfigException):
    """Exception raised when an invalid objective weight or penalty is provided."""
