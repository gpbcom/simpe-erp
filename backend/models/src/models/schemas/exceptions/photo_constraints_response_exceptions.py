class MTInvalidPhotoConstraintsResponseException(Exception):
    """Exception raised when an invalid PhotoConstraintsResponse field is provided."""


class MTPhotoConstraintsResponseInvalidMaxUploadBytes(
    MTInvalidPhotoConstraintsResponseException
):
    """Exception raised when an invalid ``max_upload_bytes`` is provided."""


class MTPhotoConstraintsResponseInvalidContentTypes(
    MTInvalidPhotoConstraintsResponseException
):
    """Exception raised when an invalid ``accepted_content_types`` is provided."""


class MTInvalidPricingRulesResponseException(Exception):
    """Exception raised when the published pricing rules are malformed."""


class MTPricingRulesResponseInvalidBaseRate(MTInvalidPricingRulesResponseException):
    """Exception raised when the agency-wide hourly rate is not positive."""


class MTPricingRulesResponseInvalidSurcharges(MTInvalidPricingRulesResponseException):
    """Exception raised when a surcharge multiplier is not a mapping."""


class MTInvalidInterventionTypeUpdateRequestException(Exception):
    """Exception raised when a catalogue-update payload is invalid."""


class MTInterventionTypeUpdateRequestInvalidName(
    MTInvalidInterventionTypeUpdateRequestException
):
    """Exception raised when the display name is empty."""


class MTInterventionTypeUpdateRequestInvalidSkills(
    MTInvalidInterventionTypeUpdateRequestException
):
    """Exception raised when an invalid ``required_skill_codes`` is given."""


class MTInterventionTypeUpdateRequestInvalidCertifications(
    MTInvalidInterventionTypeUpdateRequestException
):
    """Exception raised when the required certification codes are malformed."""


class MTInterventionTypeUpdateRequestInvalidRate(
    MTInvalidInterventionTypeUpdateRequestException
):
    """Exception raised when the hourly rate is not a positive amount."""
