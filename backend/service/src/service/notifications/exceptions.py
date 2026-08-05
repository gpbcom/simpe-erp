class MTInvalidNotificationServiceException(Exception):
    """Exception raised when a notification operation fails."""


class MTNotificationNotFound(MTInvalidNotificationServiceException):
    """Exception raised when the named notification is not the reader's.

    Notes:
        Deliberately the same exception — and so the same 404 — whether the
        notification does not exist or belongs to somebody else. Distinguishing
        the two would let a caller enumerate identifiers and learn which ones
        are real, which is a map of everything the agency has been told.
    """
