class MTInvalidPlanningRunException(Exception):
    """Exception raised when an invalid PlanningRun field is provided."""


class MTPlanningRunInvalidId(MTInvalidPlanningRunException):
    """Exception raised when an invalid identifier is provided."""


class MTPlanningRunInvalidTeamId(MTInvalidPlanningRunException):
    """Exception raised when the run does not name the team it plans.

    Notes:
        A run reads one team's accepted work and deletes one team's visits. A
        run that could not name its team would read every team's work and clear
        every team's calendar — the same failure ``company_id`` exists to close,
        one level down, and just as silent.
    """


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
