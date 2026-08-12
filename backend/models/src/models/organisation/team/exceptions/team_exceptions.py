class MTInvalidTeamException(Exception):
    """Exception raised when a team is invalid."""


class MTTeamInvalidId(MTInvalidTeamException):
    """Exception raised when the identifier is not a non-empty string."""


class MTTeamInvalidCompanyId(MTInvalidTeamException):
    """Exception raised when the owning company is not named."""


class MTTeamInvalidAgencyId(MTInvalidTeamException):
    """Exception raised when the site the team works from is not named.

    Notes:
        A team without a site has no location, and a team without a location
        cannot be the *closest* one to anybody. The tie is required rather than
        optional because the alternative is a team no quote can ever reach,
        which reads on screen exactly like a team nobody has given work to.
    """


class MTTeamInvalidName(MTInvalidTeamException):
    """Exception raised when the team name is empty or too long."""


class MTTeamInvalidManagerUserId(MTInvalidTeamException):
    """Exception raised when the team does not name exactly one manager.

    Notes:
        "Exactly one" is a cardinality, and a flag on the membership rows can
        express zero or five. A required column *is* the constraint — and the
        restricting foreign key behind it is what makes "you cannot delete this
        account while it still runs a team" a fact of the database rather than
        a service's good intentions.
    """


class MTTeamInvalidDate(MTInvalidTeamException):
    """Exception raised when a timestamp is not a datetime."""


class MTInvalidTeamMemberException(Exception):
    """Exception raised when a team membership row is invalid."""


class MTTeamMemberInvalidKind(MTInvalidTeamMemberException):
    """Exception raised when the member kind is not a :class:`MemberKind`."""


class MTTeamMemberInvalidId(MTInvalidTeamMemberException):
    """Exception raised when the member identifier is not a non-empty string."""
