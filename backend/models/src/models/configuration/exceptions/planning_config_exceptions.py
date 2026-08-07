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


class MTPlanningConfigInvalidSolverWorkers(MTInvalidPlanningConfigException):
    """Exception raised when an invalid ``solver_workers`` is provided.

    Notes:
        Zero is refused rather than read as "let the solver decide". CP-SAT
        treats it as a request for no search at all, which returns UNKNOWN
        immediately and fails every run — a failure that reads as an infeasible
        plan rather than as a misconfiguration.
    """


class MTPlanningConfigInvalidPenalty(MTInvalidPlanningConfigException):
    """Exception raised when an invalid objective weight or penalty is provided."""
