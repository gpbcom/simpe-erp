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


class MTRequirementInvalidRequiredCertifications(
    MTInvalidInterventionRequirementException
):
    """Exception raised when an invalid ``required_certification_codes`` is given."""


class MTRequirementInvalidRequiredSkills(MTInvalidInterventionRequirementException):
    """Exception raised when an invalid ``required_skill_codes`` is given."""


class MTRequirementInvalidDuration(MTInvalidInterventionRequirementException):
    """Exception raised when an invalid ``duration_minutes`` is provided."""


class MTRequirementInvalidLocation(MTInvalidInterventionRequirementException):
    """Exception raised when an invalid ``location`` value is provided."""
