class MTInvalidPlanningException(Exception):
    """Exception raised when a planning operation fails."""


class MTPlanningRunNotFound(MTInvalidPlanningException):
    """Exception raised when the named planning run does not exist."""


class MTPlanningForbidden(MTInvalidPlanningException):
    """Exception raised when a caller asks for a planning that is not theirs.

    Notes:
        Row-level, not route-level. A route guard proves the caller is *an*
        assistant; only comparing the requested assistant against their own
        record stops one reading another's diary.
    """


class MTPlanningCustomerNotFound(MTInvalidPlanningException):
    """Exception raised when a household's calendar is not the caller's to read.

    Notes:
        - **Deliberately the same answer for "does not exist" and "not yours".**
          Distinguishing the two lets a caller walk the identifier space and
          learn which households the agency serves, which is most of what a
          customer list is worth. The rule is stated once in
          ``docs/11-security.md`` and this is one of the places that keeps it.
        - Its own exception rather than the customers service's, so the planning
          service does not import another service's failures to describe its
          own.
    """


class MTPlanningPeriodTooLong(MTInvalidPlanningException):
    """Exception raised when the requested planning window is unreasonable."""


class MTPlanningSettingsUnavailable(MTInvalidPlanningException):
    """Exception raised when the rules can be neither read nor seeded.

    Notes:
        Distinct from "not seeded yet", which the service repairs on the spot.
        This means the store answered and the rules still are not there, which
        no amount of retrying by the caller will fix.
    """


class MTPlanningInfeasible(MTInvalidPlanningException):
    """Exception raised when the planning constraints cannot all be met.

    Notes:
        A run that cannot place every piece of accepted work **fails**; it does
        not succeed with gaps. A calendar missing three visits looks like a
        calendar, and the visits nobody noticed were dropped are the ones that
        end with a customer waiting at home.

        The message names each unplaced visit and why it did not fit, so the
        run record is enough to act on without re-running anything.
    """


class MTPlanningInvalidSpeed(MTInvalidPlanningException):
    """Exception raised when a configured travel speed is not usable."""


class MTPlanningInconsistentSolution(MTInvalidPlanningException):
    """Exception raised when the solver's answer breaks its own constraints."""


class MTInterventionNotFound(MTInvalidPlanningException):
    """Exception raised when the named scheduled visit does not exist."""


class MTInterventionNotQuoted(MTInvalidPlanningException):
    """Exception raised when a visit's quote line can no longer be found.

    Notes:
        A visit exists because a quote line asked for it, and every edit made
        through a visit is really an edit to that line. Without it there is
        nothing to reprice and nothing to bill, so the edit is refused rather
        than applied to the calendar alone — a calendar that disagrees with the
        paperwork is worse than an edit that did not happen.
    """


class MTPlanningTeamForbidden(MTInvalidPlanningException):
    """Exception raised when a caller plans a team they do not run.

    Notes:
        Distinct from :class:`MTPlanningForbidden`, which is about *reading*
        somebody else's planning. This one is about writing it: a run rewrites
        the named team's week, so a manager able to name a colleague's team
        could rebuild a calendar they have no part in — and the colleague would
        find out from their assistants.
    """
