from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third-party imports
from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import MemberKind
from models.geo.geo_point import GeoPoint
from models.organisation.team.team import Team
from models.organisation.team.team_member import TeamMember
from storage.mappers.organisation.team_mapper import TeamMapper
from storage.orm.organisation.agency_row import AgencyRow
from storage.orm.organisation.team_member_row import TeamMemberRow
from storage.orm.organisation.team_row import TeamRow
from storage.repositories.base import BaseRepository


class TeamRepository(BaseRepository[TeamRow]):
    """Reads and writes the teams a company delivers its work with.

    Attributes:
        mapper (TeamMapper): Converts between rows and models.

    Notes:
        - The memberships live here rather than on a repository of their own,
          for the reason
          :class:`~storage.repositories.organisation.agency.AgencyRepository`
          gives: they are part of the team's aggregate.
        - Two queries on this class carry the whole feature.
          :meth:`list_with_coordinates` is what the quote-to-team rule measures
          from, and :meth:`list_member_ids` is what the planner builds its
          workforce out of. Both are ordered, because both feed decisions that
          have to come out the same way twice.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        super().__init__(session=session, row_class=TeamRow)
        self.mapper = TeamMapper()

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_query(
        self,
        company_id: str,
        agency_id: Optional[str] = None,
        manager_user_id: Optional[str] = None,
    ) -> Select[Tuple[TeamRow]]:
        """Build the scoped select shared by the listing methods.

        Args:
            company_id (str): The company whose teams are being read.
            agency_id (Optional[str]): Restrict to one site.
            manager_user_id (Optional[str]): Restrict to the teams one account
                runs.

        Returns:
            Select[Tuple[TeamRow]]: The scoped statement, unordered.
        """
        statement = select(TeamRow).where(TeamRow.company_id == company_id)
        if agency_id:
            statement = statement.where(TeamRow.agency_id == agency_id)
        if manager_user_id:
            statement = statement.where(TeamRow.manager_user_id == manager_user_id)  # noqa: E501
        return statement

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, team: Team) -> Team:
        """Store a team.

        Args:
            team (Team): The team to store.

        Returns:
            Team: The stored team, carrying its identifier.
        """
        self.logger.info(
            "Creating team %s at agency %s, run by %s.",
            team.name,
            team.agency_id,
            team.manager_user_id,
        )
        row = self.mapper.to_row(team)
        self.session.add(row)
        await self.session.flush()
        return self.mapper.to_model(row)

    async def get(self, team_id: str) -> Optional[Team]:
        """Return a team by identifier.

        Args:
            team_id (str): The team to read.

        Returns:
            Optional[Team]: The team, or ``None`` when absent.
        """
        self.logger.debug("Fetching team %s.", team_id)
        row = await self._get_row(team_id)
        if row is None:
            self.logger.warning("Team %s does not exist.", team_id)
            return None
        return self.mapper.to_model(row)

    async def list(
        self,
        company_id: str,
        agency_id: Optional[str] = None,
        manager_user_id: Optional[str] = None,
        page: int = 1,
        size: Optional[int] = None,
    ) -> List[Team]:
        """Return a page of a company's teams, by name.

        Args:
            company_id (str): The company whose teams are being read.
            agency_id (Optional[str]): Restrict to one site.
            manager_user_id (Optional[str]): Restrict to the teams one account
                runs.
            page (int): One-based page number.
            size (Optional[int]): Page size.

        Returns:
            List[Team]: The matching teams.
        """
        self.logger.debug(
            "Listing the teams of company %s: agency=%s manager=%s page=%d.",
            company_id,
            agency_id,
            manager_user_id,
            page,
        )
        statement = self._build_query(company_id, agency_id, manager_user_id).order_by(
            TeamRow.name, TeamRow.id
        )
        rows = await self._fetch_all(self._paginate(statement, page, size))
        if not rows:
            self.logger.warning(
                "Company %s has no team matching agency=%s manager=%s.",
                company_id,
                agency_id,
                manager_user_id,
            )
        return self.mapper.to_models(rows)

    async def count(
        self,
        company_id: str,
        agency_id: Optional[str] = None,
        manager_user_id: Optional[str] = None,
    ) -> int:
        """Return how many teams match.

        Args:
            company_id (str): The company whose teams are being counted.
            agency_id (Optional[str]): Restrict to one site.
            manager_user_id (Optional[str]): Restrict to the teams one account
                runs.

        Returns:
            int: The number of teams.
        """
        total = await self._count(
            self._build_query(company_id, agency_id, manager_user_id)
        )
        self.logger.debug("Company %s has %d matching team(s).", company_id, total)  # noqa: E501
        return total

    async def list_with_coordinates(
        self, company_id: str
    ) -> List[Tuple[Team, Optional[GeoPoint]]]:
        """Return every team of a company beside its site's coordinate.

        Args:
            company_id (str): The company whose teams are being read.

        Returns:
            List[Tuple[Team, Optional[GeoPoint]]]: Each team and the point its
            site sits at, or ``None`` when the site never geocoded.

        Notes:
            - One join rather than a query per team. This runs on **every quote
              written**, so a lookup per candidate would put the attribution
              rule's cost on the number of teams a company has.
            - Ordered by identifier, and that ordering *is* the last rule of the
              attribution: closest, then least busy, then **the first**. Without
              it PostgreSQL is free to return two equally close, equally busy
              teams in either order, and the same customer would be filed
              differently on two identical runs.
            - A site with no coordinate yields ``None`` rather than being
              dropped. Its teams cannot win a distance contest, but they are
              still teams, and a company whose only site never geocoded must
              still be able to write a quote.
        """
        statement = (
            select(TeamRow, AgencyRow.latitude, AgencyRow.longitude)
            .join(AgencyRow, AgencyRow.id == TeamRow.agency_id)
            .where(TeamRow.company_id == company_id)
            .order_by(TeamRow.id)
        )
        result = await self.session.execute(statement)
        pairs: List[Tuple[Team, Optional[GeoPoint]]] = []
        for row, latitude, longitude in result.all():
            point = (
                GeoPoint(latitude=latitude, longitude=longitude)
                if latitude is not None and longitude is not None
                else None
            )
            pairs.append((self.mapper.to_model(row), point))
        self.logger.debug(
            "Read %d team(s) with their site coordinate for company %s.",
            len(pairs),
            company_id,
        )
        if not pairs:
            self.logger.warning(
                "Company %s has no team to attribute work to.", company_id
            )
        return pairs

    async def update(self, team: Team) -> Optional[Team]:
        """Replace a team's details.

        Args:
            team (Team): The team, carrying its identifier.

        Returns:
            Optional[Team]: The stored team, or ``None`` when absent.
        """
        if not team.id:
            self.logger.warning("Cannot update a team with no identifier.")
            return None
        row = await self._get_row(team.id)
        if row is None:
            self.logger.warning("Team %s does not exist.", team.id)
            return None
        self.logger.info("Updating team %s.", team.id)
        self.mapper.apply_to_row(row, team)
        await self.session.flush()
        return self.mapper.to_model(row)

    async def delete(self, team_id: str) -> bool:
        """Remove a team.

        Args:
            team_id (str): The team to remove.

        Returns:
            bool: ``True`` when a row was removed.

        Notes:
            Its memberships and its documents go with it, by cascade. Its
            quotes, runs and visits do **not** — those columns carry no foreign
            key — so the service refuses the deletion while any exist rather
            than leaving them pointing at nothing.
        """
        self.logger.info("Deleting team %s.", team_id)
        return await self._delete_row(team_id)

    async def add_member(self, team_id: str, member: TeamMember) -> TeamMember:
        """Put a person on a team.

        Args:
            team_id (str): The team they join.
            member (TeamMember): Which person, and which kind of record.

        Returns:
            TeamMember: The stored membership.

        Notes:
            A unique index refuses somebody already on a team. That refusal is
            the one that keeps a planning well-defined: two teams' runs each
            delete and rewrite their own days, so a person on both would be
            scheduled twice over the same week with nothing reporting it.
        """
        self.logger.info(
            "Putting %s %s on team %s.",
            member.member_kind.value,
            member.member_id,
            team_id,
        )
        row = self.mapper.to_member_row(team_id, member)
        self.session.add(row)
        await self.session.flush()
        return self.mapper.to_member(row)

    async def remove_member(self, member_kind: MemberKind, member_id: str) -> bool:  # noqa: E501
        """Take a person off whichever team they are on.

        Args:
            member_kind (MemberKind): Whether the identifier names an account
                or an assistant record.
            member_id (str): The account or record to remove.

        Returns:
            bool: ``True`` when a row was removed.
        """
        self.logger.info("Taking %s %s off their team.", member_kind.value, member_id)  # noqa: E501
        result = await self.session.execute(
            delete(TeamMemberRow).where(
                TeamMemberRow.member_kind == member_kind.value,
                TeamMemberRow.member_id == member_id,
            )
        )
        removed = bool(result.rowcount)
        if not removed:
            self.logger.warning("%s %s was on no team.", member_kind.value, member_id)  # noqa: E501
        return removed

    async def list_members(self, team_id: str) -> List[TeamMember]:
        """Return everybody on a team.

        Args:
            team_id (str): The team to read.

        Returns:
            List[TeamMember]: The memberships, accounts before records and each
            group by identifier.
        """
        self.logger.debug("Listing the members of team %s.", team_id)
        statement = (
            select(TeamMemberRow)
            .where(TeamMemberRow.team_id == team_id)
            .order_by(TeamMemberRow.member_kind, TeamMemberRow.member_id)
        )
        rows = await self._fetch_all(statement)
        if not rows:
            self.logger.warning("Team %s has no member.", team_id)
        return self.mapper.to_members(rows)

    async def list_member_ids(self, team_id: str, member_kind: MemberKind) -> List[str]:  # noqa: E501
        """Return the identifiers of one kind of member on a team.

        Args:
            team_id (str): The team to read.
            member_kind (MemberKind): Which kind of record to return.

        Returns:
            List[str]: The identifiers, ordered.

        Notes:
            **Ordered by identifier, and the ordering is load-bearing.** This
            list becomes the planner's workforce, and the workforce order is the
            CP-SAT variable order — so an unordered query would hand the solver
            the same week as two different models, stop the search in a
            different place, and return a different number of unplaced visits.
            The same reasoning already orders ``list_schedulable``.
        """
        statement = (
            select(TeamMemberRow.member_id)
            .where(
                TeamMemberRow.team_id == team_id,
                TeamMemberRow.member_kind == member_kind.value,
            )
            .order_by(TeamMemberRow.member_id)
        )
        result = await self.session.execute(statement)
        identifiers = [row[0] for row in result.all()]
        self.logger.debug(
            "Team %s has %d %s member(s).",
            team_id,
            len(identifiers),
            member_kind.value,
        )
        if not identifiers:
            self.logger.warning("Team %s has no %s member.", team_id, member_kind.value)  # noqa: E501
        return identifiers

    async def count_members(self, team_id: str) -> int:
        """Return how many people are on a team.

        Args:
            team_id (str): The team to count for.

        Returns:
            int: The number of members.
        """
        statement = select(TeamMemberRow).where(TeamMemberRow.team_id == team_id)  # noqa: E501
        total = await self._count(statement)
        self.logger.debug("Team %s has %d member(s).", team_id, total)
        return total

    async def team_for_member(
        self, member_kind: MemberKind, member_id: str
    ) -> Optional[Team]:
        """Return the team a person is on.

        Args:
            member_kind (MemberKind): Whether the identifier names an account
                or an assistant record.
            member_id (str): The account or record to look up.

        Returns:
            Optional[Team]: Their team, or ``None`` when they are on none.
        """
        statement = (
            select(TeamRow)
            .join(TeamMemberRow, TeamMemberRow.team_id == TeamRow.id)
            .where(
                TeamMemberRow.member_kind == member_kind.value,
                TeamMemberRow.member_id == member_id,
            )
        )
        row = await self._fetch_one(statement)
        if row is None:
            self.logger.warning("%s %s is on no team.", member_kind.value, member_id)  # noqa: E501
            return None
        return self.mapper.to_model(row)

    async def count_members_by_team(self, company_id: str) -> List[Tuple[str, int]]:  # noqa: E501
        """Return each team's member count, for a company.

        Args:
            company_id (str): The company whose teams are being counted.

        Returns:
            List[Tuple[str, int]]: Pairs of team identifier and member count.

        Notes:
            One grouped statement rather than a count per row, for the reason
            :meth:`~storage.repositories.organisation.agency.AgencyRepository.count_members_by_agency`
            gives: the teams screen shows the figure in a column.
        """
        statement = (
            select(TeamMemberRow.team_id, func.count())
            .join(TeamRow, TeamRow.id == TeamMemberRow.team_id)
            .where(TeamRow.company_id == company_id)
            .group_by(TeamMemberRow.team_id)
        )
        result = await self.session.execute(statement)
        counts = [(team_id, total) for team_id, total in result.all()]  # noqa: E501
        self.logger.debug(
            "Counted members across %d team(s) of company %s.", len(counts), company_id
        )
        return counts

    async def count_by_agency(self, company_id: str) -> List[Tuple[str, int]]:
        """Return each site's team count, for a company.

        Args:
            company_id (str): The company whose sites are being counted.

        Returns:
            List[Tuple[str, int]]: Pairs of agency identifier and team count.

        Notes:
            The bulk form of :meth:`count_for_agency`, which the sites grid
            needs one of per row. A site with no team is absent from the result
            rather than present with a zero — the caller supplies the default,
            because a grouped count has no row to group.
        """
        statement = (
            select(TeamRow.agency_id, func.count())
            .where(TeamRow.company_id == company_id)
            .group_by(TeamRow.agency_id)
        )
        result = await self.session.execute(statement)
        counts = [(agency_id, total) for agency_id, total in result.all()]
        self.logger.debug(
            "Counted teams across %d site(s) of company %s.", len(counts), company_id
        )
        return counts

    async def count_for_agency(self, agency_id: str) -> int:
        """Return how many teams work from a site.

        Args:
            agency_id (str): The site to count for.

        Returns:
            int: The number of teams.

        Notes:
            What the delete refusal is built on. A site is removable only once
            nothing works from it, and the message says how many teams do.
        """
        statement = select(TeamRow).where(TeamRow.agency_id == agency_id)
        total = await self._count(statement)
        self.logger.debug("Agency %s has %d team(s).", agency_id, total)
        return total
