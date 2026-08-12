class MTInvalidInterventionException(Exception):
    """Exception raised when an invalid Intervention field is provided."""


class MTInterventionInvalidId(MTInvalidInterventionException):
    """Exception raised when an invalid identifier is provided."""


class MTInterventionInvalidTeamId(MTInvalidInterventionException):
    """Exception raised when the visit does not name the team delivering it.

    Notes:
        A period's plan is replaced by a delete scoped to ``(company, team,
        day)``. A visit that named no team would escape every replacement for
        ever — a ghost on the calendar that no re-plan can remove.
    """


class MTInterventionInvalidName(MTInvalidInterventionException):
    """Exception raised when an invalid ``name`` value is provided."""


class MTInterventionInvalidDay(MTInvalidInterventionException):
    """Exception raised when an invalid ``day`` value is provided."""


class MTInterventionInvalidTime(MTInvalidInterventionException):
    """Exception raised when an invalid start or end time is provided."""


class MTInterventionInvalidStatus(MTInvalidInterventionException):
    """Exception raised when an invalid ``status`` value is provided."""


class MTInterventionInvalidAddress(MTInvalidInterventionException):
    """Exception raised when an invalid ``address`` value is provided."""
