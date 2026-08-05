class MTInvalidHolidaySurchargeException(Exception):
    """Exception raised when an invalid HolidaySurcharge field is provided."""


class MTHolidaySurchargeInvalidMonth(MTInvalidHolidaySurchargeException):
    """Exception raised when an invalid ``month`` value is provided."""


class MTHolidaySurchargeInvalidDay(MTInvalidHolidaySurchargeException):
    """Exception raised when an invalid ``day`` value is provided."""


class MTHolidaySurchargeInvalidSurcharge(MTInvalidHolidaySurchargeException):
    """Exception raised when an invalid ``surcharge`` value is provided."""


class MTHolidaySurchargeInvalidLabel(MTInvalidHolidaySurchargeException):
    """Exception raised when an invalid ``label`` value is provided."""
