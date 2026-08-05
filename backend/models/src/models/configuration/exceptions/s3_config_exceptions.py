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


class MTS3ConfigInvalidMaxUploadBytes(MTInvalidS3ConfigException):
    """Exception raised when an invalid ``max_upload_bytes`` is provided."""


class MTS3ConfigMissingCredentials(MTInvalidS3ConfigException):
    """Exception raised when the configured credential env vars are not set."""
