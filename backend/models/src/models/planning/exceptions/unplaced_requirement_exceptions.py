class MTInvalidUnplacedRequirementException(Exception):
    """Exception raised when an unplaced-work record is invalid."""


class MTUnplacedRequirementInvalidId(MTInvalidUnplacedRequirementException):
    """Exception raised when the requirement identifier is not a string."""


class MTUnplacedRequirementInvalidName(MTInvalidUnplacedRequirementException):
    """Exception raised when the service name is empty."""


class MTUnplacedRequirementInvalidReason(MTInvalidUnplacedRequirementException):
    """Exception raised when the reason is not a known one."""


class MTUnplacedRequirementInvalidDay(MTInvalidUnplacedRequirementException):
    """Exception raised when the day is not a date."""


class MTUnplacedRequirementInvalidDetail(MTInvalidUnplacedRequirementException):
    """Exception raised when the explanatory detail is not text."""
