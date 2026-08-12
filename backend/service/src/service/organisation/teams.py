from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# First-party imports
from models.auth.user import User
from models.enums import MemberKind, UserRole
from models.geo.geo_point import GeoPoint
from models.organisation.team.team import Team
from models.organisation.team.team_member import TeamMember
from models.people.customer.customer import Customer
from models.schemas.responses.organisation.team_view import TeamView
from service.organisation.exceptions import (
    MTTeamForbidden,
    MTTeamHasWork,
    MTTeamManagerRequired,
    MTTeamMemberAlreadyPlaced,
    MTTeamMemberOutsideAgency,
    MTTeamNameTaken,
    MTTeamNotFound,
)
from storage.repositories.auth.user import UserRepository
from storage.repositories.organisation.agency import AgencyRepository
from storage.repositories.organisation.team import TeamRepository
from storage.repositories.quoting.quote import QuoteRepository


class TeamService:
    """The teams a company delivers with, and which one gets a quote.

    Attributes:
        DISTANCE_TIE_KM (ClassVar[float]): How close two sites must be to count
            as equally close.
        teams (TeamRepository): Reads and writes the teams.
        agencies (AgencyRepository): Proves a member works at the team's site.
        users (UserRepository): Proves the named manager may run a team.
        quotes (QuoteRepository): Measures how busy each team already is.
        logger (Logger): Logger for the operations here.

    Notes:
        - :meth:`readable_team_ids` is the **one** definition of what a caller
          may see. Quotes, the workforce and the plannings all narrow by it, and
          three answers to "is this team theirs?" that could disagree would be
          worse than any one of them.
        - :meth:`attribute` is the quote-to-team rule, and it is deliberately
          the only place it is spelled. Both quote-creation paths funnel through
          ``QuoteService.create``, which calls this — two copies would drift,
          and the assistant's path is the one that would be forgotten.
    """

    DISTANCE_TIE_KM: ClassVar[float] = 0.5

    def __init__(
        self,
        teams: TeamRepository,
        agencies: AgencyRepository,
        users: UserRepository,
        quotes: QuoteRepository,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            teams (TeamRepository): Reads and writes the teams.
            agencies (AgencyRepository): Proves a member works at the site.
            users (UserRepository): Proves the named manager may run a team.
            quotes (QuoteRepository): Measures how busy each team already is.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.teams = teams
        self.agencies = agencies
        self.users = users
        self.quotes = quotes
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("TeamService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _assert_name_free(
        self, company_id: str, name: str, except_id: Optional[str] = None
    ) -> None:
        """Refuse a name another of the company's teams already uses.

        Args:
            company_id (str): The company being checked.
            name (str): The proposed name.
            except_id (Optional[str]): A team allowed to hold the name.

        Raises:
            MTTeamNameTaken: If the name is in use.
        """
        for team in await self.teams.list(company_id, page=1, size=None):
            if team.name == name and team.id != except_id:
                self.logger.warning(
                    "Company %s already has a team named %s.", company_id, name
                )
                raise MTTeamNameTaken(
                    f"This company already has a team named {name!r}."
                )

    async def _assert_manager(self, team: Team) -> None:
        """Refuse a manager who cannot run this team.

        Args:
            team (Team): The team being created or changed.

        Raises:
            MTTeamManagerRequired: If the account does not exist, does not hold
                a manager's or an administrator's role, or belongs to another
                company.

        Notes:
            Three failures, one exception, because all three are the same
            mistake from the caller's point of view: they named somebody who
            cannot do the job. The message says which.
        """
        account = await self.users.get(team.manager_user_id)
        if account is None:
            self.logger.warning(
                "Team %s names manager %s, who has no account.",
                team.name,
                team.manager_user_id,
            )
            raise MTTeamManagerRequired(
                f"No account {team.manager_user_id!r} exists to run this team."
            )
        if not account.role.is_staff() or not account.role.has_at_least(
            UserRole.MANAGER
        ):
            self.logger.warning(
                "Account %s holds role %s and cannot run a team.",
                account.id,
                account.role.value,
            )
            raise MTTeamManagerRequired(
                "A team is run by a manager or an administrator, and this "
                "account is neither."
            )
        if account.company_id != team.company_id:
            self.logger.warning(
                "Account %s of company %s cannot run a team of company %s.",
                account.id,
                account.company_id,
                team.company_id,
            )
            raise MTTeamManagerRequired(
                "This account belongs to another company and cannot run the team."
            )

    def _closest(
        self,
        candidates: List[Tuple[Team, Optional[GeoPoint]]],
        home: Optional[GeoPoint],
    ) -> List[Team]:
        """Narrow the candidates to those nearest a customer's home.

        Args:
            candidates (List[Tuple[Team, Optional[GeoPoint]]]): Every team, with
                the coordinate of the site it works from.
            home (Optional[GeoPoint]): Where the customer lives.

        Returns:
            List[Team]: The teams tied for nearest, in the order given, or every
            candidate when the distance cannot be measured at all.

        Notes:
            - A site with no coordinate is **not** treated as a distance of
              zero. Reading an unresolved address that way would put it off the
              coast of Africa and — with two such sites — make them the closest
              to everybody.
            - When nothing can be measured, every team stays a candidate and the
              busyness tie-break decides. That is the honest fallback: it is not
              "the nearest team", and the caller is told so at WARNING rather
              than being handed a proximity claim nothing supports.
        """
        located = [(team, point) for team, point in candidates if point is not None]  # noqa: E501
        if home is None or not located:
            self.logger.warning(
                "No distance could be measured for this attribution: "
                "customer_located=%s sites_located=%d.",
                home is not None,
                len(located),
            )
            return [team for team, _ in candidates]
        distances = [(team, home.distance_km(point)) for team, point in located]
        nearest = min(distance for _, distance in distances)
        return [
            team
            for team, distance in distances
            if distance - nearest <= self.DISTANCE_TIE_KM
        ]

    ############################
    # Publicly Exposed Methods #
    ############################

    async def readable_team_ids(self, caller: User) -> Optional[List[str]]:
        """Return the teams a caller may read, or ``None`` for all of them.

        Args:
            caller (User): The authenticated caller.

        Returns:
            Optional[List[str]]: ``None`` when the caller sees every team, or
            the identifiers they may see — possibly empty.

        Notes:
            **``None`` and ``[]`` are not interchangeable, and getting them
            round the wrong way opens the whole company.** ``None`` means
            *unscoped*: an administrator sees every team. ``[]`` means *nothing*:
            a manager who runs no team sees no team, and an assistant on no team
            sees no team. A caller reading a falsy value as "no filter" would
            hand the second group everything.

            **A household is answered before anything ranks**, and that ordering
            matters for the same reason it does in
            :meth:`~service.planning.plannings.PlanningService._require_staff`:
            :meth:`~models.enums.UserRole.rank` refuses to rank a customer —
            there is no rung that is correct for an axis — so asking
            ``is_manager()`` first would raise where the honest answer is simply
            "no team". Nothing routes a household here today; this is what keeps
            that true if something ever does.
        """
        if not caller.role.is_staff():
            self.logger.warning(
                "Account %s is not staff and is scoped to no team.", caller.id
            )
            return []
        if caller.is_admin():
            self.logger.debug("Account %s is an administrator: every team.", caller.id)  # noqa: E501
            return None
        if caller.is_manager():
            teams = await self.teams.list(
                caller.company_id, manager_user_id=caller.id, page=1, size=None
            )
            identifiers = [str(team.id) for team in teams]
            self.logger.debug(
                "Manager %s runs %d team(s).", caller.id, len(identifiers)
            )
            return identifiers
        if caller.hca_id:
            team = await self.teams.team_for_member(MemberKind.HCA, caller.hca_id)
            if team is None:
                self.logger.warning(
                    "Assistant %s is on no team and sees no planning.", caller.hca_id
                )
                return []
            return [str(team.id)]
        self.logger.warning(
            "Account %s is bound to no assistant record and sees no team.", caller.id
        )
        return []

    async def readable_hca_ids(self, caller: User) -> Optional[List[str]]:
        """Return the assistants a caller may read, or ``None`` for all of them.

        Args:
            caller (User): The authenticated caller.

        Returns:
            Optional[List[str]]: ``None`` when the caller sees every assistant,
            or the identifiers they may see — possibly empty.

        Notes:
            - The workforce projection of :meth:`readable_team_ids`, and it
              keeps the same contract: **``None`` means all, ``[]`` means
              none.** A caller reading the empty list as "no filter" would show
              a manager who runs no team the whole agency's staff.
            - Only ``hca`` memberships are collected. A manager who runs a team
              from an office is a member of it as an *account*, and has no
              assistant record to appear on a workforce screen.
            - Duplicates cannot arise — a person is on exactly one team — but
              the order is made deterministic anyway, so two identical requests
              produce the same page.
        """
        readable = await self.readable_team_ids(caller)
        if readable is None:
            self.logger.debug(
                "Account %s is an administrator: every assistant.", caller.id
            )
            return None
        identifiers: List[str] = []
        for team_id in readable:
            identifiers.extend(
                await self.teams.list_member_ids(team_id, MemberKind.HCA)
            )
        if not identifiers:
            self.logger.warning(
                "Account %s runs no team with anybody on it and sees no assistant.",
                caller.id,
            )
        else:
            self.logger.debug(
                "Account %s may read %d assistant(s).", caller.id, len(identifiers)
            )
        return sorted(identifiers)

    async def readable_customer_ids(self, caller: User) -> Optional[List[str]]:
        """Return the households a caller may read, or ``None`` for all.

        Args:
            caller (User): The authenticated caller.

        Returns:
            Optional[List[str]]: ``None`` when the caller sees every household,
            or the identifiers they may see — possibly empty.

        Notes:
            The household projection of :meth:`readable_team_ids`, and the third
            member of the family alongside :meth:`readable_hca_ids`. All three
            keep one contract — **``None`` means all, ``[]`` means none** — so a
            screen narrowing quotes, staff and customers cannot end up applying
            three subtly different rules.
        """
        readable = await self.readable_team_ids(caller)
        if readable is None:
            self.logger.debug(
                "Account %s is an administrator: every household.", caller.id
            )
            return None
        identifiers = await self.quotes.customer_ids_for_teams(readable)
        if not identifiers:
            self.logger.warning(
                "Account %s runs no team holding a quote and sees no household.",
                caller.id,
            )
        return identifiers

    async def get_for(self, team_id: str, caller: User) -> Team:
        """Return a team the caller is allowed to read.

        Args:
            team_id (str): The team to read.
            caller (User): The authenticated caller.

        Returns:
            Team: The team.

        Raises:
            MTTeamNotFound: If no such team exists.
            MTTeamForbidden: If it is not one the caller may read.
        """
        team = await self.teams.get(team_id)
        if team is None or team.company_id != caller.company_id:
            self.logger.warning("Account %s cannot reach team %s.", caller.id, team_id)  # noqa: E501
            raise MTTeamNotFound(f"No team {team_id!r} exists.")
        readable = await self.readable_team_ids(caller)
        if readable is not None and team_id not in readable:
            self.logger.warning("Account %s may not read team %s.", caller.id, team_id)  # noqa: E501
            raise MTTeamForbidden(f"No team {team_id!r} exists.")
        return team

    async def list_for(
        self, caller: User, page: int = 1, size: Optional[int] = None
    ) -> List[Team]:
        """Return the teams the caller may read.

        Args:
            caller (User): The authenticated caller.
            page (int): One-based page number.
            size (Optional[int]): Page size.

        Returns:
            List[Team]: The teams, by name.

        Notes:
            A manager's narrowing is applied **in the statement**, through
            ``manager_user_id``, rather than by filtering the company's teams
            afterwards — a page narrowed after the read has already loaded rows
            the caller may not see.
        """
        if caller.is_admin():
            return await self.teams.list(caller.company_id, page=page, size=size)  # noqa: E501
        if caller.is_manager():
            return await self.teams.list(
                caller.company_id,
                manager_user_id=caller.id,
                page=page,
                size=size,  # noqa: E501
            )
        readable = await self.readable_team_ids(caller)
        if not readable:
            self.logger.warning("Account %s is on no team.", caller.id)
            return []
        team = await self.teams.get(readable[0])
        return [team] if team else []

    async def views(
        self, caller: User, page: int = 1, size: Optional[int] = None
    ) -> List[TeamView]:
        """Return the teams the caller may read, ready for a grid.

        Args:
            caller (User): The authenticated caller.
            page (int): One-based page number.
            size (Optional[int]): Page size.

        Returns:
            List[TeamView]: The teams, each carrying how many people are on it.

        Notes:
            The counts come from **one grouped statement** over the company, not
            one per row. It is computed even for a manager who reads two of the
            company's teams: the extra rows are discarded by the lookup below,
            and a count keyed on the narrowed list would be a second statement
            built from the first.
        """
        teams = await self.list_for(caller, page=page, size=size)
        counts = dict(await self.teams.count_members_by_team(caller.company_id))  # noqa: E501
        self.logger.info("Serving %d team(s) to account %s.", len(teams), caller.id)
        return [
            TeamView.from_team(team, member_count=counts.get(str(team.id), 0))
            for team in teams
        ]

    async def own(self, caller: User) -> TeamView:
        """Return the team the caller is themselves on.

        Args:
            caller (User): The authenticated caller.

        Returns:
            TeamView: Their team and its member count.

        Raises:
            MTTeamNotFound: If they are on no team.

        Notes:
            **Membership, not management**, and the difference matters for a
            manager who runs two teams: they are a *member* of exactly one, and
            that is the one whose shared space and roster is theirs. The teams
            they run are a different list, served by :meth:`views`.

            The account is tried before the assistant record because a manager
            has no assistant record, and an assistant who signs in has both — the
            same order the teamspace membership check uses.
        """
        team = await self.teams.team_for_member(MemberKind.USER, str(caller.id))
        if team is None and caller.hca_id:
            team = await self.teams.team_for_member(MemberKind.HCA, caller.hca_id)  # noqa: E501
        if team is None:
            self.logger.warning("Account %s is on no team.", caller.id)
            raise MTTeamNotFound("This account is not on a team.")
        self.logger.info("Account %s is on team %s.", caller.id, team.id)
        return TeamView.from_team(
            team, member_count=await self.teams.count_members(str(team.id))
        )

    async def view(self, team_id: str, caller: User) -> TeamView:
        """Return one team the caller may read, ready for a screen.

        Args:
            team_id (str): The team to read.
            caller (User): The authenticated caller.

        Returns:
            TeamView: The team and its member count.

        Raises:
            MTTeamNotFound: If no such team exists.
            MTTeamForbidden: If it is not one the caller may read.
        """
        team = await self.get_for(team_id, caller)
        return TeamView.from_team(
            team, member_count=await self.teams.count_members(team_id)
        )

    async def create(self, team: Team, caller: User) -> Team:
        """Form a team at one of the company's sites.

        Args:
            team (Team): The team to create, carrying the caller's company.
            caller (User): The administrator forming it.

        Returns:
            Team: The stored team, with its manager already a member.

        Raises:
            MTTeamNameTaken: If the company already has a team of that name.
            MTTeamManagerRequired: If the named manager cannot run it.
            MTTeamMemberAlreadyPlaced: If the manager is already on a team.

        Notes:
            **The manager is added as a member by the same call.** It costs one
            row and buys the literal reading of "a team is a list of persons",
            so a roster never has to explain why the person in charge is missing
            from it.
        """
        await self._assert_name_free(team.company_id, team.name)
        await self._assert_manager(team)
        self.logger.info(
            "Forming team %s at agency %s, run by %s, requested by %s.",
            team.name,
            team.agency_id,
            team.manager_user_id,
            caller.id,
        )
        created = await self.teams.create(team)
        await self.add_member(
            str(created.id),
            TeamMember(member_kind=MemberKind.USER, member_id=team.manager_user_id),  # noqa: E501
            caller,
        )
        return created

    async def update(self, team: Team, caller: User) -> Team:
        """Change a team's name, site or manager.

        Args:
            team (Team): The team, carrying its identifier.
            caller (User): The administrator making the change.

        Returns:
            Team: The stored team.

        Raises:
            MTTeamNotFound: If no such team exists.
            MTTeamNameTaken: If another team already uses the name.
            MTTeamManagerRequired: If the named manager cannot run it.
        """
        stored = await self.teams.get(str(team.id))
        if stored is None or stored.company_id != caller.company_id:
            self.logger.warning("Team %s does not exist.", team.id)
            raise MTTeamNotFound(f"No team {team.id!r} exists.")
        await self._assert_name_free(stored.company_id, team.name, stored.id)
        merged = team.model_copy(
            update={"id": stored.id, "company_id": stored.company_id}
        )
        await self._assert_manager(merged)
        self.logger.info("Updating team %s, requested by %s.", stored.id, caller.id)  # noqa: E501
        updated = await self.teams.update(merged)
        if updated is None:
            self.logger.error("Team %s vanished while being updated.", stored.id)  # noqa: E501
            raise MTTeamNotFound(f"No team {stored.id!r} exists.")
        return updated

    async def delete(self, team_id: str, caller: User) -> None:
        """Disband a team.

        Args:
            team_id (str): The team to remove.
            caller (User): The administrator disbanding it.

        Raises:
            MTTeamNotFound: If no such team exists.
            MTTeamHasWork: If quotes still name it.

        Notes:
            ``quotes.team_id`` carries no foreign key, so nothing stops a quote
            outliving its team — and a quote naming a team that no longer exists
            is one no planning run will ever read again. The refusal names the
            count, because the answer is to move that work to another team.
        """
        team = await self.teams.get(team_id)
        if team is None or team.company_id != caller.company_id:
            self.logger.warning("Team %s does not exist.", team_id)
            raise MTTeamNotFound(f"No team {team_id!r} exists.")
        held = await self.quotes.count_for_team(team_id)
        if held:
            self.logger.warning(
                "Refusing to delete team %s: %d quote(s) still name it.",
                team_id,
                held,
            )
            raise MTTeamHasWork(
                f"This team still holds {held} quote(s). Move them to another "
                f"team first, or they will never be planned again."
            )
        self.logger.info("Disbanding team %s, requested by %s.", team_id, caller.id)  # noqa: E501
        await self.teams.delete(team_id)

    async def members(self, team_id: str, caller: User) -> List[TeamMember]:
        """Return everybody on a team the caller may read.

        Args:
            team_id (str): The team to read.
            caller (User): The authenticated caller.

        Returns:
            List[TeamMember]: The memberships.

        Raises:
            MTTeamNotFound: If no such team exists.
            MTTeamForbidden: If it is not one the caller may read.
        """
        await self.get_for(team_id, caller)
        return await self.teams.list_members(team_id)

    async def add_member(
        self, team_id: str, member: TeamMember, caller: User
    ) -> TeamMember:
        """Put somebody on a team.

        Args:
            team_id (str): The team they join.
            member (TeamMember): Which person, and which kind of record.
            caller (User): The administrator adding them.

        Returns:
            TeamMember: The stored membership.

        Raises:
            MTTeamNotFound: If no such team exists.
            MTTeamMemberAlreadyPlaced: If they are already on a team.
            MTTeamMemberOutsideAgency: If they do not work at the team's site.

        Notes:
            The site check is not a formality. A team is people *at a place*,
            and the planner measures every round from that place — so somebody
            based elsewhere would be routed from a depot they never travel to.
        """
        team = await self.teams.get(team_id)
        if team is None or team.company_id != caller.company_id:
            self.logger.warning("Team %s does not exist.", team_id)
            raise MTTeamNotFound(f"No team {team_id!r} exists.")

        existing = await self.teams.team_for_member(
            member.member_kind, member.member_id
        )
        if existing is not None:
            self.logger.warning(
                "%s %s is already on team %s.",
                member.member_kind.value,
                member.member_id,
                existing.id,
            )
            raise MTTeamMemberAlreadyPlaced(
                f"This person is already on {existing.name!r}. Take them off "
                f"that team first."
            )

        site = await self.agencies.agency_for_member(
            member.member_kind, member.member_id
        )
        if site is None or site.id != team.agency_id:
            self.logger.warning(
                "%s %s works at agency %s, not at %s.",
                member.member_kind.value,
                member.member_id,
                site.id if site else None,
                team.agency_id,
            )
            raise MTTeamMemberOutsideAgency(
                "This person does not work at the site this team is based at. "
                "Attach them to that site first."
            )

        self.logger.info(
            "Putting %s %s on team %s, requested by %s.",
            member.member_kind.value,
            member.member_id,
            team_id,
            caller.id,
        )
        return await self.teams.add_member(team_id, member)

    async def remove_member(
        self,
        team_id: str,
        member_kind: MemberKind,
        member_id: str,
        caller: User,  # noqa: E501
    ) -> None:
        """Take somebody off a team.

        Args:
            team_id (str): The team they leave.
            member_kind (MemberKind): Whether the identifier names an account
                or an assistant record.
            member_id (str): The account or record to remove.
            caller (User): The administrator removing them.

        Raises:
            MTTeamNotFound: If no such team exists, or they are not on it.
            MTTeamManagerRequired: If they are the team's manager.

        Notes:
            The manager cannot be removed while they still run the team. A team
            with no manager is a team whose re-plan button belongs to nobody,
            and the column that says so is ``NOT NULL`` — so the removal would
            simply fail later, with a message about a database constraint rather
            than about who runs what.
        """
        team = await self.teams.get(team_id)
        if team is None or team.company_id != caller.company_id:
            self.logger.warning("Team %s does not exist.", team_id)
            raise MTTeamNotFound(f"No team {team_id!r} exists.")
        if member_kind is MemberKind.USER and team.is_managed_by(member_id):
            self.logger.warning(
                "Refusing to take manager %s off the team they run.", member_id
            )
            raise MTTeamManagerRequired(
                "This account runs the team. Name a different manager first."
            )
        removed = await self.teams.remove_member(member_kind, member_id)
        if not removed:
            self.logger.warning(
                "%s %s is not on team %s.", member_kind.value, member_id, team_id
            )
            raise MTTeamNotFound(
                f"No {member_kind.value} {member_id!r} is on this team."
            )
        self.logger.info(
            "Took %s %s off team %s, requested by %s.",
            member_kind.value,
            member_id,
            team_id,
            caller.id,
        )

    async def detach_person(self, member_kind: MemberKind, member_id: str) -> None:  # noqa: E501
        """Take somebody off whichever team they are on.

        Args:
            member_kind (MemberKind): Whether the identifier names an account
                or an assistant record.
            member_id (str): The account or record being deleted.

        Notes:
            Called by the person-deletion paths, and silent when there is
            nothing to remove. Nothing cascades — the column is polymorphic and
            carries no foreign key — so a deleted assistant whose membership
            survived would stay in the planner's workforce and be scheduled for
            visits nobody can attend.
        """
        removed = await self.teams.remove_member(member_kind, member_id)
        if removed:
            self.logger.info(
                "Took %s %s off their team as their record is removed.",
                member_kind.value,
                member_id,
            )
        else:
            self.logger.debug(
                "%s %s was on no team; nothing to detach.",
                member_kind.value,
                member_id,
            )

    async def attribute(self, company_id: str, customer: Customer) -> Optional[str]:  # noqa: E501
        """Return the team a new quote for this customer belongs to.

        Args:
            company_id (str): The company writing the quote.
            customer (Customer): The household the quote is addressed to.

        Returns:
            Optional[str]: The team's identifier, or ``None`` when the company
            has no team to attribute work to.

        Notes:
            The rule, in order, and each step is here because the one before it
            can tie:

            1. every team of the company is a candidate;
            2. keep those whose **site is nearest** the customer's home, within
               :attr:`DISTANCE_TIE_KM`;
            3. among those, the one carrying the **fewest assigned minutes** —
               measured over live quotes rather than planned visits, so a
               company that has never run the planner still spreads work;
            4. among those, **the first**, which is why every query behind this
               is ordered by identifier. Without it two equally close, equally
               busy teams come back in either order and the same household is
               filed differently on two identical runs.

            ``None`` rather than an exception, because *which* failure it was
            belongs to the caller: ``QuoteService`` turns it into a refusal
            naming the reason, and the seeder treats it as "not yet".
        """
        candidates = await self.teams.list_with_coordinates(company_id)
        if not candidates:
            self.logger.warning(
                "Company %s has no team; a quote cannot be attributed.", company_id
            )
            return None

        home = customer.address.to_geo_point() if customer.address else None
        nearest = self._closest(candidates, home)
        if len(nearest) == 1:
            self.logger.info(
                "Quote for customer %s goes to team %s: nearest site.",
                customer.id,
                nearest[0].id,
            )
            return str(nearest[0].id)

        identifiers = [str(team.id) for team in nearest]
        minutes = await self.quotes.assigned_minutes_by_team(company_id, identifiers)
        least = min(minutes[team_id] for team_id in identifiers)
        chosen = next(team for team in nearest if minutes[str(team.id)] == least)
        self.logger.info(
            "Quote for customer %s goes to team %s: %d team(s) equally close, "
            "and it carries %d minute(s).",
            customer.id,
            chosen.id,
            len(nearest),
            least,
        )
        return str(chosen.id)
