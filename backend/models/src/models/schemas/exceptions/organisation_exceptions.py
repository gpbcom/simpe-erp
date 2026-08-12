class MTInvalidAgencyCreateRequestException(Exception):
    """Exception raised when a payload opening a new site is invalid."""


class MTAgencyCreateRequestInvalidName(MTInvalidAgencyCreateRequestException):
    """Exception raised when the site name is empty or too long."""


class MTAgencyCreateRequestInvalidType(MTInvalidAgencyCreateRequestException):
    """Exception raised when the site type is not a known ``AgencyType``."""


class MTInvalidAgencyUpdateRequestException(Exception):
    """Exception raised when a payload changing a site is invalid."""


class MTAgencyUpdateRequestInvalidName(MTInvalidAgencyUpdateRequestException):
    """Exception raised when the site name is empty or too long."""


class MTAgencyUpdateRequestInvalidType(MTInvalidAgencyUpdateRequestException):
    """Exception raised when the site type is not a known ``AgencyType``."""


class MTInvalidTeamCreateRequestException(Exception):
    """Exception raised when a payload forming a team is invalid."""


class MTTeamCreateRequestInvalidName(MTInvalidTeamCreateRequestException):
    """Exception raised when the team name is empty or too long."""


class MTTeamCreateRequestInvalidAgencyId(MTInvalidTeamCreateRequestException):
    """Exception raised when the site the team works from is not named."""


class MTTeamCreateRequestInvalidManagerUserId(MTInvalidTeamCreateRequestException):
    """Exception raised when the account meant to run the team is not named."""


class MTInvalidTeamUpdateRequestException(Exception):
    """Exception raised when a payload changing a team is invalid."""


class MTTeamUpdateRequestInvalidName(MTInvalidTeamUpdateRequestException):
    """Exception raised when the team name is empty or too long."""


class MTTeamUpdateRequestInvalidAgencyId(MTInvalidTeamUpdateRequestException):
    """Exception raised when the site the team works from is not named."""


class MTTeamUpdateRequestInvalidManagerUserId(MTInvalidTeamUpdateRequestException):
    """Exception raised when the account meant to run the team is not named."""


class MTInvalidAgencyViewException(Exception):
    """Exception raised when a projected site is malformed."""


class MTAgencyViewInvalidName(MTInvalidAgencyViewException):
    """Exception raised when the projected site has no name."""


class MTAgencyViewInvalidCount(MTInvalidAgencyViewException):
    """Exception raised when a headline count is negative or not an integer."""


class MTInvalidTeamViewException(Exception):
    """Exception raised when a projected team is malformed."""


class MTTeamViewInvalidName(MTInvalidTeamViewException):
    """Exception raised when the projected team has no name."""


class MTTeamViewInvalidCount(MTInvalidTeamViewException):
    """Exception raised when the member count is negative or not an integer."""


class MTInvalidTeamDocumentConstraintsResponseException(Exception):
    """Exception raised when the published teamspace limits are malformed."""


class MTTeamDocumentConstraintsResponseInvalidMaxUploadBytes(
    MTInvalidTeamDocumentConstraintsResponseException
):
    """Exception raised when the published size limit is not positive."""


class MTTeamDocumentConstraintsResponseInvalidContentTypes(
    MTInvalidTeamDocumentConstraintsResponseException
):
    """Exception raised when the published media types are malformed."""
