class MTInvalidQuoteTypeWeekAggregateException(Exception):
    """Exception raised when an invalid aggregate field is provided."""


class MTAggregateInvalidInterventionTypeId(MTInvalidQuoteTypeWeekAggregateException):
    """Exception raised when an invalid ``intervention_type_id`` is provided."""


class MTAggregateInvalidInterventionTypeName(MTInvalidQuoteTypeWeekAggregateException):
    """Exception raised when an invalid ``intervention_type_name`` is given."""


class MTAggregateInvalidIsoYear(MTInvalidQuoteTypeWeekAggregateException):
    """Exception raised when an invalid ``iso_year`` value is provided."""


class MTAggregateInvalidIsoWeek(MTInvalidQuoteTypeWeekAggregateException):
    """Exception raised when an invalid ``iso_week`` value is provided."""


class MTAggregateInvalidWeekStart(MTInvalidQuoteTypeWeekAggregateException):
    """Exception raised when an invalid ``week_start_date`` is provided."""


class MTAggregateInvalidCount(MTInvalidQuoteTypeWeekAggregateException):
    """Exception raised when an invalid count value is provided."""


class MTAggregateInvalidAmount(MTInvalidQuoteTypeWeekAggregateException):
    """Exception raised when an invalid money amount is provided."""
