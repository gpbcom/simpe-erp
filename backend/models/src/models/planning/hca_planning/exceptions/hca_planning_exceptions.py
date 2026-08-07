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
