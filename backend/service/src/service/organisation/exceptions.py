class MTInvalidAgencyServiceException(Exception):
    """Exception raised when an operation on a site fails."""


class MTAgencyNotFound(MTInvalidAgencyServiceException):
    """Exception raised when the named site does not exist."""


class MTAgencyForbidden(MTInvalidAgencyServiceException):
    """Exception raised when a site belongs to another company.

    Notes:
        Answered as a **404**, not a 403, like every other cross-tenancy read in
        this codebase. Telling the two apart lets a caller walk the identifier
        space and learn how many places a competitor operates from, which is
        most of what a site list is worth.
    """


class MTAgencyNameTaken(MTInvalidAgencyServiceException):
    """Exception raised when the company already has a site of that name."""


class MTAgencyHeadquartersProtected(MTInvalidAgencyServiceException):
    """Exception raised when the head office would be lost or duplicated.

    Notes:
        Covers both directions of the same rule: a second head office cannot be
        created, and the only one cannot be retyped or deleted while other
        sites still refer to the company. A company whose head office vanished
        would have no answer to "where is this business registered", and the
        next site created would silently be promoted into the gap.
    """


class MTAgencyNotEmpty(MTInvalidAgencyServiceException):
    """Exception raised when a site still holds teams or people.

    Notes:
        The message names both counts. "This agency cannot be deleted" without
        a number is a refusal nobody can act on — the two answers are *move the
        teams* and *move the people*, and they go to different screens.
    """


class MTAgencyMemberRunsATeam(MTInvalidAgencyServiceException):
    """Exception raised when moving somebody would leave a team unmanaged.

    Notes:
        Attaching somebody to a site **moves** them off whichever one they were
        on, and takes them off a team based at the old site — a team is people
        at a place, and the planner measures every round from that place.

        This is the one case that cannot be handled that way. A team's manager
        is a required column, so there is no state in which a team briefly has
        none, and choosing a replacement is not a decision a site transfer
        should make silently. The message names the team, because naming a new
        manager is the action.
    """


class MTAgencyMemberOutsideCompany(MTInvalidAgencyServiceException):
    """Exception raised when the person named belongs to another company.

    Notes:
        The membership tables carry no foreign key on ``member_id`` — the
        column is polymorphic — so this service is the only thing standing
        between a payload and a row pointing at somebody else's workforce.
    """


class MTInvalidTeamServiceException(Exception):
    """Exception raised when an operation on a team fails."""


class MTTeamNotFound(MTInvalidTeamServiceException):
    """Exception raised when the named team does not exist."""


class MTTeamForbidden(MTInvalidTeamServiceException):
    """Exception raised when a team is not one the caller may read.

    Notes:
        Answered as a **404**, for the reason
        :class:`MTAgencyForbidden` gives. A manager narrowed to their own teams
        must not be able to count the others.
    """


class MTTeamNameTaken(MTInvalidTeamServiceException):
    """Exception raised when the company already has a team of that name."""


class MTTeamManagerRequired(MTInvalidTeamServiceException):
    """Exception raised when the named manager cannot run the team.

    Notes:
        Three ways to fail one rule: the account does not exist, it does not
        hold a manager's or an administrator's role, or it belongs to a
        different company. All three answer 422 because all three are a payload
        naming somebody who cannot do the job.
    """


class MTTeamMemberManagesAnother(MTInvalidTeamServiceException):
    """Exception raised when moving somebody would leave a team unmanaged.

    Notes:
        Putting somebody on a team **moves** them off whichever one they were
        on: a person is on exactly one team either way, and requiring the
        operator to remove them first would be two forms for one act.

        This is the case that cannot be handled that way. A team's manager is a
        required column, so there is no state in which a team briefly has none,
        and picking a replacement is not a decision this call should make
        silently. The message names the team, because naming a new manager is
        the action.
    """


class MTTeamMemberOutsideAgency(MTInvalidTeamServiceException):
    """Exception raised when a member does not work at the team's site.

    Notes:
        A team is people *at a place*. Somebody based elsewhere joining it would
        be routed from a depot they never travel to, and the planner would build
        rounds out of a distance that is not the one they drive.
    """


class MTTeamHasWork(MTInvalidTeamServiceException):
    """Exception raised when a team still holds quotes, runs or visits.

    Notes:
        Those three columns carry no foreign key, so nothing cascades and
        nothing stops the rows outliving the team. Deleting anyway would leave
        quotes no run ever reads and visits no re-plan can ever clear — so the
        refusal names the counts and the answer is to reassign them first.
    """


class MTInvalidTeamDocumentServiceException(Exception):
    """Exception raised when an operation on a shared document fails."""


class MTTeamDocumentNotFound(MTInvalidTeamDocumentServiceException):
    """Exception raised when the named document does not exist.

    Notes:
        Also what a non-member is told, deliberately. A team's shared space is
        private, and a 403 would confirm a document exists to somebody with no
        business knowing it does.
    """


class MTTeamDocumentForbidden(MTInvalidTeamDocumentServiceException):
    """Exception raised when the caller may not remove a document.

    Notes:
        Distinct from :class:`MTTeamDocumentNotFound` on purpose, and answered
        as a 403. Everybody on a team may *read* every document in its space, so
        the existence of one is not a secret from them — what is refused is a
        member deleting a colleague's file, and being told "no such document"
        for something they can plainly see would read as a bug.
    """


class MTTeamDocumentStorageUnavailable(MTInvalidTeamDocumentServiceException):
    """Exception raised when a document operation runs with no object store.

    Notes:
        Answered as a 503, because it describes the deployment rather than the
        request: the same call will work once an object store is configured, and
        nothing the caller can change about the payload will help.
    """
