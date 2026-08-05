class MTInvalidInterventionRequirementException(Exception):
    """Exception raised when an invalid requirement field is provided."""


class MTRequirementInvalidId(MTInvalidInterventionRequirementException):
    """Exception raised when an invalid identifier is provided."""


class MTRequirementInvalidName(MTInvalidInterventionRequirementException):
    """Exception raised when an invalid ``name`` value is provided."""


class MTRequirementInvalidDay(MTInvalidInterventionRequirementException):
    """Exception raised when an invalid ``day`` value is provided."""


class MTRequirementInvalidWindow(MTInvalidInterventionRequirementException):
    """Exception raised when an invalid window bound is provided."""


class MTRequirementInvalidDuration(MTInvalidInterventionRequirementException):
    """Exception raised when an invalid ``duration_minutes`` is provided."""


class MTRequirementInvalidLocation(MTInvalidInterventionRequirementException):
    """Exception raised when an invalid ``location`` value is provided."""


class MTInvalidInterventionException(Exception):
    """Exception raised when an invalid Intervention field is provided."""


class MTInterventionInvalidId(MTInvalidInterventionException):
    """Exception raised when an invalid identifier is provided."""


class MTInterventionInvalidName(MTInvalidInterventionException):
    """Exception raised when an invalid ``name`` value is provided."""


class MTInterventionInvalidDay(MTInvalidInterventionException):
    """Exception raised when an invalid ``day`` value is provided."""


class MTInterventionInvalidTime(MTInvalidInterventionException):
    """Exception raised when an invalid start or end time is provided."""


class MTInterventionInvalidStatus(MTInvalidInterventionException):
    """Exception raised when an invalid ``status`` value is provided."""


class MTInterventionInvalidAddress(MTInvalidInterventionException):
    """Exception raised when an invalid ``address`` value is provided."""


class MTInvalidHcaPlanningException(Exception):
    """Exception raised when an invalid HcaPlanning field is provided."""


class MTPlanningInvalidHcaId(MTInvalidHcaPlanningException):
    """Exception raised when an invalid ``hca_id`` value is provided."""


class MTPlanningInvalidHcaName(MTInvalidHcaPlanningException):
    """Exception raised when an invalid ``hca_full_name`` value is provided."""


class MTPlanningInvalidPeriod(MTInvalidHcaPlanningException):
    """Exception raised when an invalid planning period is provided."""


class MTPlanningInvalidInterventions(MTInvalidHcaPlanningException):
    """Exception raised when an invalid ``interventions`` list is provided."""


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
