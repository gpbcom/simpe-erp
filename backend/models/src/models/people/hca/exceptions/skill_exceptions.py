class MTInvalidSkillException(Exception):
    """Exception raised when an invalid Skill field is provided."""


class MTSkillInvalidId(MTInvalidSkillException):
    """Exception raised when an invalid ``id`` value is provided.

    Notes:
        A skill is deleted by identifier, which is what makes this field
        load-bearing in a way a certification's is not: a blank one would
        address no row, and the delete would report success having removed
        nothing.
    """


class MTSkillInvalidName(MTInvalidSkillException):
    """Exception raised when an invalid ``name`` value is provided."""


class MTSkillInvalidCode(MTInvalidSkillException):
    """Exception raised when an invalid ``code`` value is provided.

    Notes:
        The code is what the planner matches a requirement against. A
        malformed one would match nothing and quietly leave its holder
        unqualified, so it is refused rather than stored.
    """


class MTSkillInvalidIssuer(MTInvalidSkillException):
    """Exception raised when an invalid ``issuer`` value is provided."""


class MTSkillInvalidObtainedOn(MTInvalidSkillException):
    """Exception raised when an invalid ``obtained_on`` value is provided."""


class MTSkillInvalidExpiresOn(MTInvalidSkillException):
    """Exception raised when an invalid ``expires_on`` value is provided."""
