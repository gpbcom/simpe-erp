class MTInvalidMapperException(Exception):
    """Exception raised when a model cannot be mapped onto its row."""


class MTInterventionMissingPlanningRun(MTInvalidMapperException):
    """Exception raised when a visit names no planning run to belong to.

    Notes:
        A visit is only ever produced by a run, and the run is what a manager
        re-reads, re-runs or discards. One stored without that link is a visit
        nothing accounts for, so the write is refused rather than performed.
    """
