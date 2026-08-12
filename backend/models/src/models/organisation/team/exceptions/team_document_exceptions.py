class MTInvalidTeamDocumentException(Exception):
    """Exception raised when a shared team document is invalid."""


class MTTeamDocumentInvalidId(MTInvalidTeamDocumentException):
    """Exception raised when the identifier is not a non-empty string."""


class MTTeamDocumentInvalidTeamId(MTInvalidTeamDocumentException):
    """Exception raised when the owning team is not named."""


class MTTeamDocumentInvalidCompanyId(MTInvalidTeamDocumentException):
    """Exception raised when the owning company is not named."""


class MTTeamDocumentInvalidFileName(MTInvalidTeamDocumentException):
    """Exception raised when the file name is empty, too long or a path.

    Notes:
        A name carrying a separator is refused rather than sanitised. It is
        rendered as a link and echoed into a ``Content-Disposition`` header, and
        a value quietly stripped of its ``../`` is a value somebody meant to be
        dangerous — worth a refusal somebody sees rather than a repair nobody
        does.
    """


class MTTeamDocumentInvalidContentType(MTInvalidTeamDocumentException):
    """Exception raised when the content type is not a usable media type.

    Notes:
        The stored value is the one the object store *sniffed*, never the one
        the upload declared, so this refuses a malformed record rather than a
        malicious upload. The upload's own refusal is
        :class:`~storage.s3.exceptions.s3_exceptions.MTS3UnsupportedContentType`.
    """


class MTTeamDocumentInvalidSizeBytes(MTInvalidTeamDocumentException):
    """Exception raised when the recorded size is not a positive integer."""


class MTTeamDocumentInvalidDocumentKey(MTInvalidTeamDocumentException):
    """Exception raised when the object key is not under the team prefix.

    Notes:
        The key is what an authenticated download resolves, so one pointing
        outside the application's own team-document prefix would let a stored
        record address any object in the bucket — the invoices among them.
    """


class MTTeamDocumentInvalidUploadedBy(MTInvalidTeamDocumentException):
    """Exception raised when the uploading account is not named."""


class MTTeamDocumentInvalidDate(MTInvalidTeamDocumentException):
    """Exception raised when a timestamp is not a datetime."""
