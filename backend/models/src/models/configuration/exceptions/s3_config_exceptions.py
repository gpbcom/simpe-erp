class MTInvalidS3ConfigException(Exception):
    """Exception raised when an invalid S3Config field is provided."""


class MTS3ConfigInvalidBucket(MTInvalidS3ConfigException):
    """Exception raised when an invalid ``bucket`` value is provided."""


class MTS3ConfigInvalidRegion(MTInvalidS3ConfigException):
    """Exception raised when an invalid ``region`` value is provided."""


class MTS3ConfigInvalidEndpointUrl(MTInvalidS3ConfigException):
    """Exception raised when an invalid ``endpoint_url`` value is provided."""


class MTS3ConfigInvalidPublicBaseUrl(MTInvalidS3ConfigException):
    """Exception raised when an invalid ``public_base_url`` is provided."""


class MTS3ConfigInvalidCredentialEnv(MTInvalidS3ConfigException):
    """Exception raised when an invalid credential env-var name is provided."""


class MTS3ConfigInvalidPhotoPrefix(MTInvalidS3ConfigException):
    """Exception raised when an invalid ``photo_key_prefix`` is provided."""


class MTS3ConfigInvalidLogoPrefix(MTInvalidS3ConfigException):
    """Exception raised when an invalid ``logo_key_prefix`` is provided."""


class MTS3ConfigInvalidInvoicePrefix(MTInvalidS3ConfigException):
    """Exception raised when an invalid ``invoice_key_prefix`` is provided.

    Notes:
        Its own class rather than a shared one, for the reason the photo and
        logo prefixes have theirs: the API's exception-to-status map is keyed on
        the class, and a rejected invoice prefix reporting itself as a bad photo
        prefix would send whoever is fixing the deployment to the wrong line.
    """


class MTS3ConfigInvalidMaxUploadBytes(MTInvalidS3ConfigException):
    """Exception raised when an invalid ``max_upload_bytes`` is provided."""


class MTS3ConfigMissingCredentials(MTInvalidS3ConfigException):
    """Exception raised when the configured credential env vars are not set."""


class MTS3ConfigInvalidTeamDocumentPrefix(MTInvalidS3ConfigException):
    """Exception raised when the team-document key prefix is unusable.

    Notes:
        Shares the rule every prefix follows and, like the invoice one, guards
        objects that are written private and never handed to a browser. A wrong
        value there does not merely misplace a team's shared paperwork — it puts
        it under a prefix the download check no longer recognises, so every file
        already stored becomes unreachable.
    """
