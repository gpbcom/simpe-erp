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
