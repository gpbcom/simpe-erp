from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third-party imports
from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import AgencyType, MemberKind
from models.organisation.agency.agency import Agency
from models.organisation.agency.agency_member import AgencyMember
from storage.mappers.organisation.agency_mapper import AgencyMapper
from storage.orm.organisation.agency_member_row import AgencyMemberRow
from storage.orm.organisation.agency_row import AgencyRow
from storage.repositories.base import BaseRepository


class AgencyRepository(BaseRepository[AgencyRow]):
    """Reads and writes a company's places, and who works at each.

    Attributes:
        mapper (AgencyMapper): Converts between rows and models.

    Notes:
        - The memberships live on this repository rather than on one of their
          own, because they are part of the site's aggregate: a membership is
          never read except through the site it points at, and one repository
          per table would put two objects between a service and one question.
        - Every read is scoped by ``company_id``. A site list that could return
          another company's places would publish where a competitor operates
          from — and, worse, offer them in the team form.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        super().__init__(session=session, row_class=AgencyRow)
        self.mapper = AgencyMapper()

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_query(self, company_id: str) -> Select[Tuple[AgencyRow]]:
        """Build the company-scoped select shared by the listing methods.

        Args:
            company_id (str): The company whose sites are being read.

        Returns:
            Select[Tuple[AgencyRow]]: The scoped statement, unordered.
        """
        return select(AgencyRow).where(AgencyRow.company_id == company_id)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, agency: Agency) -> Agency:
        """Store a site.

        Args:
            agency (Agency): The site to store.

        Returns:
            Agency: The stored site, carrying its identifier.
        """
        self.logger.info(
            "Creating %s agency %s for company %s.",
            agency.agency_type.value,
            agency.name,
            agency.company_id,
        )
        row = self.mapper.to_row(agency)
        self.session.add(row)
        await self.session.flush()
        return self.mapper.to_model(row)

    async def get(self, agency_id: str) -> Optional[Agency]:
        """Return a site by identifier.

        Args:
            agency_id (str): The site to read.

        Returns:
            Optional[Agency]: The site, or ``None`` when absent.
        """
        self.logger.debug("Fetching agency %s.", agency_id)
        row = await self._get_row(agency_id)
        if row is None:
            self.logger.warning("Agency %s does not exist.", agency_id)
            return None
        return self.mapper.to_model(row)

    async def list(
        self,
        company_id: str,
        page: int = 1,
        size: Optional[int] = None,
    ) -> List[Agency]:
        """Return a page of a company's sites, by name.

        Args:
            company_id (str): The company whose sites are being read.
            page (int): One-based page number.
            size (Optional[int]): Page size.

        Returns:
            List[Agency]: The matching sites.

        Notes:
            Ordered by name and then by identifier. The second key looks
            redundant against a unique ``(company_id, name)`` index and is not:
            it is what makes the order total even while a rename is in flight,
            and the attribution rule's final tie-break is "the first".
        """
        self.logger.debug(
            "Listing the agencies of company %s: page=%d.", company_id, page
        )
        statement = self._build_query(company_id).order_by(AgencyRow.name, AgencyRow.id)  # noqa: E501   # noqa: E501  # noqa: E501
        rows = await self._fetch_all(self._paginate(statement, page, size))
        if not rows:
            self.logger.warning("Company %s has no agency.", company_id)
        return self.mapper.to_models(rows)

    async def count(self, company_id: str) -> int:
        """Return how many sites a company has.

        Args:
            company_id (str): The company to count for.

        Returns:
            int: The number of sites.

        Notes:
            This is what decides whether a new site is the head office. It is a
            count rather than a "does an HQ exist" probe because the rule is
            about the *first* site, and a company whose head office was deleted
            and re-created must not silently mint a second one.
        """
        total = await self._count(self._build_query(company_id))
        self.logger.debug("Company %s has %d agency(ies).", company_id, total)
        return total

    async def headquarters(self, company_id: str) -> Optional[Agency]:
        """Return a company's head office, if it has one.

        Args:
            company_id (str): The company to read.

        Returns:
            Optional[Agency]: The head office, or ``None``.

        Notes:
            A partial unique index makes at most one row match, so this returns
            a single site rather than a list. The seeder calls it before
            deriving an identifier of its own — a migrated database already has
            a head office, and creating a second one would leave the people in
            one and the quotes in the other.
        """
        statement = self._build_query(company_id).where(
            AgencyRow.agency_type == AgencyType.HQ.value
        )
        row = await self._fetch_one(statement)
        if row is None:
            self.logger.warning("Company %s has no headquarters.", company_id)
            return None
        return self.mapper.to_model(row)

    async def update(self, agency: Agency) -> Optional[Agency]:
        """Replace a site's details.

        Args:
            agency (Agency): The site, carrying its identifier.

        Returns:
            Optional[Agency]: The stored site, or ``None`` when absent.
        """
        if not agency.id:
            self.logger.warning("Cannot update an agency with no identifier.")
            return None
        row = await self._get_row(agency.id)
        if row is None:
            self.logger.warning("Agency %s does not exist.", agency.id)
            return None
        self.logger.info("Updating agency %s.", agency.id)
        self.mapper.apply_to_row(row, agency)
        await self.session.flush()
        return self.mapper.to_model(row)

    async def delete(self, agency_id: str) -> bool:
        """Remove a site.

        Args:
            agency_id (str): The site to remove.

        Returns:
            bool: ``True`` when a row was removed.

        Notes:
            Its memberships go with it, by cascade. Its **teams do not** — that
            foreign key restricts — so a site still holding one refuses at the
            database. The service counts both first and says which, because
            "this agency cannot be deleted" without a number is a message
            nobody can act on.
        """
        self.logger.info("Deleting agency %s.", agency_id)
        return await self._delete_row(agency_id)

    async def add_member(self, agency_id: str, member: AgencyMember) -> AgencyMember:  # noqa: E501
        """Attach a person to a site.

        Args:
            agency_id (str): The site they join.
            member (AgencyMember): Which person, and which kind of record.

        Returns:
            AgencyMember: The stored membership.

        Notes:
            A unique index refuses somebody who already belongs to a site, so
            moving a person is a remove and an add rather than an insert that
            quietly wins. The service does the removal deliberately. Letting an
            insert overwrite would make "which site is this person at?" depend
            on which form was saved last.
        """
        self.logger.info(
            "Attaching %s %s to agency %s.",
            member.member_kind.value,
            member.member_id,
            agency_id,
        )
        row = self.mapper.to_member_row(agency_id, member)
        self.session.add(row)
        await self.session.flush()
        return self.mapper.to_member(row)

    async def remove_member(self, member_kind: MemberKind, member_id: str) -> bool:  # noqa: E501
        """Detach a person from whichever site they belong to.

        Args:
            member_kind (MemberKind): Whether the identifier names an account
                or an assistant record.
            member_id (str): The account or record to detach.

        Returns:
            bool: ``True`` when a row was removed.

        Notes:
            The site is **not** a parameter, and that is deliberate: a person
            belongs to exactly one, so naming it would let a caller pass the
            wrong one and be told nothing happened. This is also the method the
            person-deletion paths call, where the site is not known at all.
        """
        self.logger.info(
            "Detaching %s %s from their agency.", member_kind.value, member_id
        )
        result = await self.session.execute(
            delete(AgencyMemberRow).where(
                AgencyMemberRow.member_kind == member_kind.value,
                AgencyMemberRow.member_id == member_id,
            )
        )
        removed = bool(result.rowcount)
        if not removed:
            self.logger.warning(
                "%s %s belonged to no agency.", member_kind.value, member_id
            )
        return removed

    async def list_members(self, agency_id: str) -> List[AgencyMember]:
        """Return everybody attached to a site.

        Args:
            agency_id (str): The site to read.

        Returns:
            List[AgencyMember]: The memberships, accounts before records and
            each group by identifier.
        """
        self.logger.debug("Listing the members of agency %s.", agency_id)
        statement = (
            select(AgencyMemberRow)
            .where(AgencyMemberRow.agency_id == agency_id)
            .order_by(AgencyMemberRow.member_kind, AgencyMemberRow.member_id)
        )
        rows = await self._fetch_all(statement)
        if not rows:
            self.logger.warning("Agency %s has no member.", agency_id)
        return self.mapper.to_members(rows)

    async def count_members(self, agency_id: str) -> int:
        """Return how many people are attached to a site.

        Args:
            agency_id (str): The site to count for.

        Returns:
            int: The number of members.
        """
        statement = select(AgencyMemberRow).where(
            AgencyMemberRow.agency_id == agency_id
        )
        total = await self._count(statement)
        self.logger.debug("Agency %s has %d member(s).", agency_id, total)
        return total

    async def agency_for_member(
        self, member_kind: MemberKind, member_id: str
    ) -> Optional[Agency]:
        """Return the site a person belongs to.

        Args:
            member_kind (MemberKind): Whether the identifier names an account
                or an assistant record.
            member_id (str): The account or record to look up.

        Returns:
            Optional[Agency]: Their site, or ``None`` when they belong to none.
        """
        statement = (
            select(AgencyRow)
            .join(AgencyMemberRow, AgencyMemberRow.agency_id == AgencyRow.id)
            .where(
                AgencyMemberRow.member_kind == member_kind.value,
                AgencyMemberRow.member_id == member_id,
            )
        )
        row = await self._fetch_one(statement)
        if row is None:
            self.logger.warning(
                "%s %s belongs to no agency.", member_kind.value, member_id
            )
            return None
        return self.mapper.to_model(row)

    async def count_members_by_agency(self, company_id: str) -> List[Tuple[str, int]]:  # noqa: E501
        """Return each site's member count, for a company.

        Args:
            company_id (str): The company whose sites are being counted.

        Returns:
            List[Tuple[str, int]]: Pairs of site identifier and member count.

        Notes:
            One grouped statement rather than a count per row. The sites screen
            shows the figure in a column, and a query per row is the shape that
            looks fine on the seeded three and is unusable at thirty.
        """
        statement = (
            select(AgencyMemberRow.agency_id, func.count())
            .join(AgencyRow, AgencyRow.id == AgencyMemberRow.agency_id)
            .where(AgencyRow.company_id == company_id)
            .group_by(AgencyMemberRow.agency_id)
        )
        result = await self.session.execute(statement)
        counts = [(agency_id, total) for agency_id, total in result.all()]
        self.logger.debug(
            "Counted members across %d agency(ies) of company %s.",
            len(counts),
            company_id,
        )
        return counts
