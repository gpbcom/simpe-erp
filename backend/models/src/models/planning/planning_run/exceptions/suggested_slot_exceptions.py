class MTInvalidSuggestedSlotException(Exception):
    """Exception raised when an offered replacement slot is invalid."""


class MTSuggestedSlotInvalidDay(MTInvalidSuggestedSlotException):
    """Exception raised when the day is not a date."""


class MTSuggestedSlotInvalidMinute(MTInvalidSuggestedSlotException):
    """Exception raised when a minute-of-day is outside a single day."""


class MTSuggestedSlotInvalidWindow(MTInvalidSuggestedSlotException):
    """Exception raised when the slot does not run forwards."""


class MTSuggestedSlotInvalidAssistant(MTInvalidSuggestedSlotException):
    """Exception raised when the assistant offering the slot is not named."""
