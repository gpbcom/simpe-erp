class MTInvalidInterventionTypeException(Exception):
    """Exception raised when an invalid InterventionType field is provided."""


class MTInterventionTypeInvalidId(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``id`` value is provided."""


class MTInterventionTypeInvalidName(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``name`` value is provided."""


class MTInterventionTypeInvalidCode(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``code`` value is provided."""


class MTInterventionTypeInvalidDescription(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``description`` value is provided."""


class MTInterventionTypeInvalidServiceCategory(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``service_category`` is provided."""


class MTInterventionTypeInvalidHourlyRate(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``base_hourly_rate_ht`` is provided."""


class MTInterventionTypeInvalidIsActive(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``is_active`` value is provided."""


class MTInterventionTypeInvalidRequiredCertifications(
    MTInvalidInterventionTypeException
):
    """Exception raised when an invalid ``required_certification_codes`` is given.

    Notes:
        A malformed requirement is refused rather than dropped. Silently
        ignoring an entry would schedule an unqualified assistant on work the
        agency believed was gated, which is the one failure this field exists
        to prevent.
    """


class MTInterventionTypeInvalidRequiredSkills(MTInvalidInterventionTypeException):
    """Exception raised when an invalid ``required_skill_codes`` is given.

    Notes:
        Distinct from the certification exception beside it even though the
        rule is character-for-character the same. The two requirements are
        satisfied from different places — a manager records a certification,
        an assistant declares a skill — so a message naming the wrong one
        sends somebody to the wrong screen.
    """


class MTInterventionTypeInvalidDate(MTInvalidInterventionTypeException):
    """Exception raised when an invalid timestamp value is provided."""
