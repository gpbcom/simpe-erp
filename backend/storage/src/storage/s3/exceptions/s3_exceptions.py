class MTInvalidS3StorageException(Exception):
    """Exception raised when an object-store operation fails."""


class MTS3UploadFailed(MTInvalidS3StorageException):
    """Exception raised when an object could not be written."""


class MTS3DeleteFailed(MTInvalidS3StorageException):
    """Exception raised when an object could not be removed."""


class MTS3BucketUnavailable(MTInvalidS3StorageException):
    """Exception raised when the configured bucket cannot be reached."""


class MTS3UnsupportedContentType(MTInvalidS3StorageException):
    """Exception raised when the uploaded file is not an accepted image."""


class MTS3PayloadTooLarge(MTInvalidS3StorageException):
    """Exception raised when the uploaded file exceeds the configured size."""


class MTS3EmptyPayload(MTInvalidS3StorageException):
    """Exception raised when the uploaded file carries no bytes."""
