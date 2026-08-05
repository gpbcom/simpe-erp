class MTInvalidAvailabilitySlotException(Exception):
    """Exception raised when an invalid AvailabilitySlot field is provided."""


class MTAvailabilitySlotInvalidId(MTInvalidAvailabilitySlotException):
    """Exception raised when an invalid ``id`` value is provided."""


class MTAvailabilitySlotInvalidHcaId(MTInvalidAvailabilitySlotException):
    """Exception raised when an invalid ``hca_id`` value is provided."""


class MTAvailabilitySlotInvalidStartDate(MTInvalidAvailabilitySlotException):
    """Exception raised when an invalid ``start_date`` value is provided."""


class MTAvailabilitySlotInvalidEndDate(MTInvalidAvailabilitySlotException):
    """Exception raised when an invalid ``end_date`` value is provided."""


class MTAvailabilitySlotInvalidKind(MTInvalidAvailabilitySlotException):
    """Exception raised when an invalid ``kind`` value is provided."""


class MTAvailabilitySlotInvalidStartTime(MTInvalidAvailabilitySlotException):
    """Exception raised when an invalid ``start_time`` value is provided."""


class MTAvailabilitySlotInvalidEndTime(MTInvalidAvailabilitySlotException):
    """Exception raised when an invalid ``end_time`` value is provided."""


class MTAvailabilitySlotInvalidNote(MTInvalidAvailabilitySlotException):
    """Exception raised when an invalid ``note`` value is provided."""
