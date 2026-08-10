"""Every list screen's filter exceptions, one family per screen.

Notes:
    Grouped in one module because they are one kind of thing, and split into one
    family per screen because the API's exception-to-status map is keyed on the
    class: a rejected assistant filter reporting itself as a quote one would
    send whoever is debugging it to the wrong screen.

    Each family derives from
    :class:`~models.base.exceptions.MTInvalidEntityFilterException`, so the map
    needs a single row for the rule they all share while still being able to
    answer any one of them specifically.
"""

from models.base.exceptions import MTInvalidEntityFilterException


class MTInvalidQuoteFilterException(MTInvalidEntityFilterException):
    """Exception raised when a quote filter is invalid."""


class MTQuoteFilterInvalidFragment(MTInvalidQuoteFilterException):
    """Exception raised when a quote text filter is not a string."""


class MTQuoteFilterInvalidFlag(MTInvalidQuoteFilterException):
    """Exception raised when a quote filter flag is not a boolean."""


class MTQuoteFilterInvalidStatus(MTInvalidQuoteFilterException):
    """Exception raised when the quote status filter is not a known status."""


class MTInvalidHcaFilterException(MTInvalidEntityFilterException):
    """Exception raised when an assistant filter is invalid."""


class MTHcaFilterInvalidFragment(MTInvalidHcaFilterException):
    """Exception raised when an assistant text filter is not a string."""


class MTHcaFilterInvalidFlag(MTInvalidHcaFilterException):
    """Exception raised when an assistant filter flag is not a boolean."""


class MTHcaFilterInvalidContractType(MTInvalidHcaFilterException):
    """Exception raised when the contract-type filter is not a known type."""


class MTInvalidInterventionTypeFilterException(MTInvalidEntityFilterException):
    """Exception raised when a catalogue filter is invalid."""


class MTInterventionTypeFilterInvalidFragment(
    MTInvalidInterventionTypeFilterException
):
    """Exception raised when a catalogue text filter is not a string."""


class MTInterventionTypeFilterInvalidFlag(MTInvalidInterventionTypeFilterException):
    """Exception raised when a catalogue filter flag is not a boolean."""


class MTInterventionTypeFilterInvalidCategory(
    MTInvalidInterventionTypeFilterException
):
    """Exception raised when the service-category filter is not a known one."""


class MTInvalidCertificationTypeFilterException(MTInvalidEntityFilterException):
    """Exception raised when a certification filter is invalid."""


class MTCertificationTypeFilterInvalidFragment(
    MTInvalidCertificationTypeFilterException
):
    """Exception raised when a certification text filter is not a string."""


class MTCertificationTypeFilterInvalidFlag(MTInvalidCertificationTypeFilterException):
    """Exception raised when a certification filter flag is not a boolean."""


class MTInvalidSkillTypeFilterException(MTInvalidEntityFilterException):
    """Exception raised when a skill filter is invalid."""


class MTSkillTypeFilterInvalidFragment(MTInvalidSkillTypeFilterException):
    """Exception raised when a skill text filter is not a string."""


class MTSkillTypeFilterInvalidFlag(MTInvalidSkillTypeFilterException):
    """Exception raised when a skill filter flag is not a boolean."""


class MTInvalidNotificationFilterException(MTInvalidEntityFilterException):
    """Exception raised when a notification filter is invalid."""


class MTNotificationFilterInvalidFragment(MTInvalidNotificationFilterException):
    """Exception raised when a notification text filter is not a string."""


class MTNotificationFilterInvalidFlag(MTInvalidNotificationFilterException):
    """Exception raised when a notification filter flag is not a boolean."""


class MTNotificationFilterInvalidKind(MTInvalidNotificationFilterException):
    """Exception raised when the notification-kind filter is not a known kind."""
