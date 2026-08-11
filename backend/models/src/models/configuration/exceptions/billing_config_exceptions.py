class MTInvalidBillingConfigException(Exception):
    """Exception raised when an invalid BillingConfig field is provided."""


class MTBillingConfigInvalidPeriodicity(MTInvalidBillingConfigException):
    """Exception raised when the seeded periodicity is unknown."""


class MTBillingConfigInvalidPaymentTerms(MTInvalidBillingConfigException):
    """Exception raised when the seeded payment terms are out of range."""


class MTBillingConfigInvalidPenaltyMultiplier(MTInvalidBillingConfigException):
    """Exception raised when the seeded penalty multiplier is out of range."""


class MTBillingConfigInvalidIndemnity(MTInvalidBillingConfigException):
    """Exception raised when the seeded recovery indemnity is invalid."""
