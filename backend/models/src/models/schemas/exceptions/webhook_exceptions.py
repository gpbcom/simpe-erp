class MTInvalidPlanningCompletedRequestException(Exception):
    """Exception raised when an invalid PlanningCompletedRequest field is provided."""


class MTPlanningCompletedRequestInvalidRunId(
    MTInvalidPlanningCompletedRequestException
):
    """Exception raised when an invalid ``run_id`` value is provided."""


class MTInvalidEmailDispatchResponseException(Exception):
    """Exception raised when an invalid EmailDispatchResponse field is provided."""


class MTEmailDispatchResponseInvalidCount(MTInvalidEmailDispatchResponseException):
    """Exception raised when an invalid delivery count is provided."""
