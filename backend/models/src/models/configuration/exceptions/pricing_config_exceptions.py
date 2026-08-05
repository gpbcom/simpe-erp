class MTInvalidPricingConfigException(Exception):
    """Exception raised when an invalid PricingConfig field is provided."""


class MTPricingConfigInvalidBaseHourlyRate(MTInvalidPricingConfigException):
    """Exception raised when an invalid ``base_hourly_rate_ht`` is provided."""


class MTPricingConfigInvalidWeekdaySurcharges(MTInvalidPricingConfigException):
    """Exception raised when an invalid ``weekday_surcharges`` map is provided."""


class MTPricingConfigInvalidHolidaySurcharges(MTInvalidPricingConfigException):
    """Exception raised when an invalid ``holiday_surcharges`` list is provided."""
