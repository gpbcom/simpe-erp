class MTInvalidBillingSettingsException(Exception):
    """Exception raised when an invalid BillingSettings field is provided."""


class MTBillingSettingsInvalidId(MTInvalidBillingSettingsException):
    """Exception raised when the identifier is not the singleton row's."""


class MTBillingSettingsInvalidPeriodicity(MTInvalidBillingSettingsException):
    """Exception raised when the billing periodicity is missing or unknown."""


class MTBillingSettingsInvalidPaymentTerms(MTInvalidBillingSettingsException):
    """Exception raised when the payment terms are outside the legal range.

    Notes:
        The ceiling is statutory rather than a preference: the code de commerce
        caps agreed payment terms, so a value above it would print an obligation
        the agency could not enforce.
    """


class MTBillingSettingsInvalidPenaltyMultiplier(MTInvalidBillingSettingsException):
    """Exception raised when the late-payment multiplier is below the floor."""


class MTBillingSettingsInvalidIndemnity(MTInvalidBillingSettingsException):
    """Exception raised when the recovery indemnity is not a positive amount."""


class MTBillingSettingsInvalidUpdatedBy(MTInvalidBillingSettingsException):
    """Exception raised when the editing account is not identified."""


class MTBillingSettingsInvalidDate(MTInvalidBillingSettingsException):
    """Exception raised when an invalid timestamp value is provided."""
