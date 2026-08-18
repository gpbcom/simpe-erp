from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import ClassVar, List, Optional, Type

# First-party imports
from models.auth.user import User
from models.enums import AgencyType, MemberKind
from models.organisation.agency.agency import Agency
from models.organisation.agency.agency_member import AgencyMember
from models.schemas.responses.organisation.agency_view import AgencyView
from service.organisation.base import AbstractOrganisationService
from service.organisation.exceptions import (
    MTAgencyForbidden,
    MTAgencyHeadquartersProtected,
    MTAgencyMemberRunsATeam,
    MTAgencyNameTaken,
    MTAgencyNotEmpty,
    MTAgencyNotFound,
)
from storage.repositories.companies.company import CompanyRepository
from storage.repositories.organisation.agency import AgencyRepository
from storage.repositories.organisation.team import TeamRepository


class AgencyService(AbstractOrganisationService[Agency, AgencyView]):
    """The places a company operates from, and who works at each.

    Attributes:
        agencies (AgencyRepository): Reads and writes the sites.
        companies (CompanyRepository): Read for the legal identity a head
            office inherits.
        teams (TeamRepository): Consulted before a site is removed.
        logger (Logger): Logger for the operations here.

    Notes:
        - **The first site of a company is its head office, and the payload has
          no say in it.** The rule is here rather than on the model because it
          is a question about *other rows*, which a value cannot answer about
          itself, and it is enforced a second time by a partial unique index —
          so a race between two administrators creating the first site ends with
          one refusal rather than two head offices.
        - Every method takes the caller and checks the site belongs to their
          company. The route guard proves the *rank*; only this layer can prove
          the *row*, because nothing at the routing layer stops an administrator
          putting another company's identifier in the path.
    """

    entity_label: ClassVar[str] = "agency"
    unreachable_exc: ClassVar[Type[Exception]] = MTAgencyForbidden
    name_taken_exc: ClassVar[Type[Exception]] = MTAgencyNameTaken

    def __init__(
        self,
        agencies: AgencyRepository,
        companies: CompanyRepository,
        teams: TeamRepository,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            agencies (AgencyRepository): Reads and writes the sites.
            companies (CompanyRepository): Read for the legal identity a
                head office inherits.
            teams (TeamRepository): Consulted before a site is removed.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        super().__init__(logger)
        self.agencies = agencies
        self.companies = companies
        self.teams = teams

    ############################
    # Internal Helpers Methods #
    ############################

    async def _get(self, entity_id: str) -> Optional[Agency]:
        """Return a site by identifier, or ``None``."""
        return await self.agencies.get(entity_id)

    async def _list_for_company(
        self, company_id: str, *, page: int = 1, size: Optional[int] = None
    ) -> List[Agency]:
        """Return a company's sites, for the name-uniqueness scan."""
        return await self.agencies.list(company_id, page=page, size=size)

    async def _to_view(self, agency: Agency) -> AgencyView:
        """Project one site onto its screen representation.

        Notes:
            The per-site counts are used here rather than the grouped ones: one
            row needs two counts, and the grouped form would read the whole
            company to answer about a single site.
        """
        return AgencyView.from_agency(
            agency,
            member_count=await self.agencies.count_members(str(agency.id)),
            team_count=await self.teams.count_for_agency(str(agency.id)),
        )

    async def _to_views(self, agencies: List[Agency], caller: User) -> List[AgencyView]:
        """Project a page of sites onto their screen representation.

        Notes:
            - The two counts come from **one grouped statement each**, not one
              per row. A page of twenty sites otherwise costs forty-one queries,
              and the grid is the first screen an administrator opens.
            - A site nothing is attached to is absent from both results, so the
              default is supplied here rather than by the database. A grouped
              count has no row to group when there is nothing to count.
            - Projecting is what makes these routes safe to open to every signed
              in account: a site *is* a
              :class:`~models.organisation.companies.company.Company` and carries
              the IBAN, which
              :class:`~models.schemas.responses.organisation.agency_view.AgencyView`
              does not declare.
        """
        members = dict(await self.agencies.count_members_by_agency(caller.company_id))  # noqa: E501
        teams = dict(await self.teams.count_by_agency(caller.company_id))
        self.logger.info(
            "Serving %d site(s) of company %s to account %s.",
            len(agencies),
            caller.company_id,
            caller.id,
        )
        return [
            AgencyView.from_agency(
                agency,
                member_count=members.get(str(agency.id), 0),
                team_count=teams.get(str(agency.id), 0),
            )
            for agency in agencies
        ]

    async def _with_legal_identity(self, agency: Agency) -> Agency:
        """Copy the company's legal identity onto a head office.

        Args:
            agency (Agency): The head office being opened.

        Returns:
            Agency: The same site, carrying the business's identity.

        Notes:
            - An :class:`~models.organisation.agency.agency.Agency` *is* a
              :class:`~models.organisation.companies.company.Company`: the head
              office is where the business is registered, and a quote prints its
              SIRET, its VAT number and its bank details from the site it was
              written at. Taking those from the company at creation is what
              makes the two agree without a join at print time.
            - **Only fields the payload left empty are filled.** An
              administrator who typed a corrected RCS entry into the form meant
              it, and overwriting it with the company's stale one would make the
              form look broken.
            - A head office that ends up holding none of it is logged at
              ``WARNING`` rather than refused. Every one of these fields is
              optional on a company, so a young agency legitimately has none —
              but a quote will print without a SIRET, and that is worth saying
              once here rather than discovering on a customer's document.
        """
        company = await self.companies.get(agency.company_id)
        if company is None:
            self.logger.error(
                "Company %s does not exist. Its head office is opened without "
                "a legal identity.",
                agency.company_id,
            )
            return agency
        inherited = {
            field: getattr(company, field)
            for field in Agency.LEGAL_IDENTITY_FIELDS
            if getattr(agency, field) is None
        }
        merged = agency.model_copy(update=inherited) if inherited else agency
        if not merged.holds_legal_identity():
            self.logger.warning(
                "The head office of company %s carries no legal identity: its "
                "quotes and invoices will print without a registration number.",
                agency.company_id,
            )
        else:
            self.logger.debug(
                "Copied %d legal-identity field(s) from company %s onto its "
                "head office.",
                len(inherited),
                agency.company_id,
            )
        return merged

    async def _release_team(self, agency_id: str, member: AgencyMember) -> None:  # noqa: E501
        """Take somebody off a team that is based somewhere they no longer work.

        Args:
            agency_id (str): The site they are moving to.
            member (AgencyMember): The person moving.

        Raises:
            MTAgencyMemberRunsATeam: If they run the team they would leave.

        Notes:
            - Called before the site membership is rewritten, because once it
              has been the person is on a team at the wrong place and nothing
              distinguishes that from an ordinary state.
            - A team based at the **same** site is kept. Moving between teams at
              one site is a different act, done on the teams screen, and a site
              transfer that also reshuffled teams would be doing two things at
              once.
            - The manager is the refusal, and it is the only one left. A team
              whose manager is gone is a team nobody may re-plan: ``manager_id``
              is required, so there is no state in which it briefly has none.
        """
        team = await self.teams.team_for_member(member.member_kind, member.member_id)
        if team is None or team.agency_id == agency_id:
            return
        if member.member_kind is MemberKind.USER and team.is_managed_by(
            member.member_id
        ):
            self.logger.warning(
                "Account %s runs team %s at agency %s and cannot be moved away "
                "from it.",
                member.member_id,
                team.id,
                team.agency_id,
            )
            raise MTAgencyMemberRunsATeam(
                f"This person runs {team.name!r}, which is based at another "
                f"site. Name a new manager for that team first."
            )
        self.logger.warning(
            "Moving %s %s to agency %s also takes them off team %s, which is "
            "based at agency %s.",
            member.member_kind.value,
            member.member_id,
            agency_id,
            team.id,
            team.agency_id,
        )
        await self.teams.remove_member(member.member_kind, member.member_id)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, agency: Agency, caller: User) -> Agency:
        """Open a new site for the caller's company.

        Args:
            agency (Agency): The site to create, carrying the caller's company.
            caller (User): The administrator opening it.

        Returns:
            Agency: The stored site.

        Raises:
            MTAgencyNameTaken: If the company already has a site of that name.
            MTAgencyHeadquartersProtected: If it would be a second head office.

        Notes:
            The type is **decided here and overwritten**, whatever the payload
            said: the first site of a company is its head office, and every one
            after it is a branch until somebody deliberately changes it. A
            payload able to choose would let the second administrator through
            the door declare their own office the head one.
        """
        await self._assert_name_free(agency.company_id, agency.name)
        existing = await self.agencies.count(agency.company_id)
        resolved_type = AgencyType.HQ if existing == 0 else AgencyType.OFFICE
        if agency.agency_type.is_headquarters() and resolved_type is not AgencyType.HQ:  # noqa: E501
            self.logger.warning(
                "Company %s already has a headquarters; refusing a second.",
                agency.company_id,
            )
            raise MTAgencyHeadquartersProtected(
                "This company already has a head office. Only one site may be "
                "the head office."
            )
        proposed = agency.model_copy(update={"agency_type": resolved_type})
        if resolved_type.is_headquarters():
            proposed = await self._with_legal_identity(proposed)
        self.logger.info(
            "Opening %s agency %s for company %s, requested by %s.",
            resolved_type.value,
            agency.name,
            agency.company_id,
            caller.id,
        )
        return await self.agencies.create(proposed)

    async def update(self, agency: Agency, caller: User) -> Agency:
        """Change a site's name, address or type.

        Args:
            agency (Agency): The site, carrying its identifier.
            caller (User): The administrator making the change.

        Returns:
            Agency: The stored site.

        Raises:
            MTAgencyNotFound: If no such site exists.
            MTAgencyForbidden: If it belongs to another company.
            MTAgencyNameTaken: If another site already uses the name.
            MTAgencyHeadquartersProtected: If the change would move or
                duplicate the head office.

        Notes:
            - The head office cannot be demoted and no branch can be promoted
              into a second one. Moving it is deliberately not offered here: it
              would mean two writes that must both succeed, and a half-applied
              move leaves a company with none.
            - **Only the three site fields are taken from the argument**. The
              rest is kept from the stored record. A site inherits its company's
              legal identity, so storing the argument whole would let a form
              that asks for a name and an address blank the SIRET and the
              account every invoice is paid into.
        """
        stored = await self._owned(str(agency.id), caller)
        await self._assert_name_free(stored.company_id, agency.name, stored.id)
        if stored.is_headquarters() != agency.agency_type.is_headquarters():
            self.logger.warning(
                "Refusing to change the type of agency %s to %s.",
                stored.id,
                agency.agency_type.value,
            )
            raise MTAgencyHeadquartersProtected(
                "Which site is the head office cannot be changed here. Only one "
                "site may hold it, and moving it would leave the company with "
                "none if the second write failed."
            )
        self.logger.info("Updating agency %s, requested by %s.", stored.id, caller.id)  # noqa: E501
        updated = await self.agencies.update(
            stored.model_copy(
                update={
                    "name": agency.name,
                    "address": agency.address,
                    "agency_type": agency.agency_type,
                }
            )
        )
        if updated is None:
            self.logger.error("Agency %s vanished while being updated.", stored.id)  # noqa: E501
            raise MTAgencyNotFound(f"No agency {stored.id!r} exists.")
        return updated

    async def delete(self, agency_id: str, caller: User) -> None:
        """Close a site.

        Args:
            agency_id (str): The site to remove.
            caller (User): The administrator closing it.

        Raises:
            MTAgencyNotFound: If no such site exists.
            MTAgencyForbidden: If it belongs to another company.
            MTAgencyNotEmpty: If teams or people are still attached.
            MTAgencyHeadquartersProtected: If it is the last head office and
                other sites remain.

        Notes:
            The counts are in the message because they are the actionable part:
            teams are moved from one screen and people from another, and a bare
            "cannot be deleted" sends somebody to look for both.
        """
        agency = await self._owned(agency_id, caller)
        teams = await self.teams.count_for_agency(agency_id)
        members = await self.agencies.count_members(agency_id)
        if teams or members:
            self.logger.warning(
                "Refusing to delete agency %s: %d team(s) and %d member(s).",
                agency_id,
                teams,
                members,
            )
            raise MTAgencyNotEmpty(
                f"This site still holds {teams} team(s) and {members} "
                f"member(s). Move them to another site first."
            )
        if (
            agency.is_headquarters()
            and await self.agencies.count(agency.company_id) > 1
        ):
            self.logger.warning(
                "Refusing to delete the headquarters of company %s while %d "
                "other site(s) remain.",
                agency.company_id,
                await self.agencies.count(agency.company_id) - 1,
            )
            raise MTAgencyHeadquartersProtected(
                "The head office cannot be closed while the company still "
                "operates from other sites."
            )
        self.logger.info("Closing agency %s, requested by %s.", agency_id, caller.id)  # noqa: E501
        await self.agencies.delete(agency_id)

    async def members(self, agency_id: str, caller: User) -> List[AgencyMember]:  # noqa: E501
        """Return everybody attached to one of the caller's company's sites.

        Args:
            agency_id (str): The site to read.
            caller (User): The authenticated caller.

        Returns:
            List[AgencyMember]: The memberships.

        Raises:
            MTAgencyNotFound: If no such site exists.
            MTAgencyForbidden: If it belongs to another company.
        """
        await self._owned(agency_id, caller)
        return await self.agencies.list_members(agency_id)

    async def add_member(
        self, agency_id: str, member: AgencyMember, caller: User
    ) -> AgencyMember:
        """Attach somebody to a site, moving them off whichever one they were on.

        Args:
            agency_id (str): The site they join.
            member (AgencyMember): Which person, and which kind of record.
            caller (User): The administrator attaching them.

        Returns:
            AgencyMember: The stored membership.

        Raises:
            MTAgencyNotFound: If no such site exists.
            MTAgencyForbidden: If it belongs to another company.
            MTAgencyMemberRunsATeam: If they run a team based at the site they
                are leaving.

        Notes:
            - **A move, not a refusal.** Somebody transferring between sites does
              it once, on one screen; making them detach first would be two
              forms for one act, and the state in between — a person attached to
              no site at all — is one nothing else in the system expects.
              Everybody belongs to exactly one site, and the unique index says
              so, so the old membership has to go either way. The only question
              was whether the operator had to do it by hand.
            - **Their team goes with the old site.** A team is people *at a
              place*, and the planner measures every round from that place — so
              somebody kept on a team based where they no longer work would be
              routed from a depot they never travel to. They come off it, and
              the move is logged at ``WARNING`` because it is a consequence
              nobody asked for on screen.
            - **Unless they run that team**, which is the one case still
              refused. Taking the manager off would leave a team nobody may
              re-plan, and choosing a replacement is not a decision a site
              transfer should make silently. The message names the team, because
              naming a new manager is the action.
        """
        await self._owned(agency_id, caller)
        existing = await self.agencies.agency_for_member(
            member.member_kind, member.member_id
        )
        if existing is not None and existing.id == agency_id:
            self.logger.debug(
                "%s %s already works at agency %s. Nothing to move.",
                member.member_kind.value,
                member.member_id,
                agency_id,
            )
            return member

        await self._release_team(agency_id, member)
        if existing is not None:
            self.logger.info(
                "Moving %s %s from agency %s to agency %s, requested by %s.",
                member.member_kind.value,
                member.member_id,
                existing.id,
                agency_id,
                caller.id,
            )
            await self.agencies.remove_member(member.member_kind, member.member_id)
        else:
            self.logger.info(
                "Attaching %s %s to agency %s, requested by %s.",
                member.member_kind.value,
                member.member_id,
                agency_id,
                caller.id,
            )
        return await self.agencies.add_member(agency_id, member)

    async def remove_member(
        self,
        agency_id: str,
        member_kind: MemberKind,
        member_id: str,
        caller: User,  # noqa: E501
    ) -> None:
        """Detach somebody from a site.

        Args:
            agency_id (str): The site they leave.
            member_kind (MemberKind): Whether the identifier names an account
                or an assistant record.
            member_id (str): The account or record to detach.
            caller (User): The administrator detaching them.

        Raises:
            MTAgencyNotFound: If no such site exists, or the person is not on
                it.
            MTAgencyForbidden: If the site belongs to another company.

        Notes:
            Taking somebody off a site does **not** take them off their team.
            The two are separate acts because a team is refused a member from
            outside its site, so the screen has to be able to do them in the
            order that leaves no invalid state in between.
        """
        await self._owned(agency_id, caller)
        removed = await self.agencies.remove_member(member_kind, member_id)
        if not removed:
            self.logger.warning(
                "%s %s is not attached to agency %s.",
                member_kind.value,
                member_id,
                agency_id,
            )
            raise MTAgencyNotFound(
                f"No {member_kind.value} {member_id!r} "  # noqa: E501
                "is attached to this site."
            )
        self.logger.info(
            "Detached %s %s from agency %s, requested by %s.",
            member_kind.value,
            member_id,
            agency_id,
            caller.id,
        )

    async def detach_person(self, member_kind: MemberKind, member_id: str) -> None:  # noqa: E501
        """Remove somebody from whichever site they belong to.

        Args:
            member_kind (MemberKind): Whether the identifier names an account
                or an assistant record.
            member_id (str): The account or record being deleted.

        Notes:
            Called by the person-deletion paths, and deliberately silent when
            there is nothing to remove. The membership tables carry no foreign
            key on ``member_id`` — the column is polymorphic — so nothing
            cascades, and a deleted assistant whose membership survived would
            put a ghost on a roster and in a planning workforce.
        """
        removed = await self.agencies.remove_member(member_kind, member_id)
        if removed:
            self.logger.info(
                "Detached %s %s from their agency as their record is removed.",
                member_kind.value,
                member_id,
            )
        else:
            self.logger.debug(
                "%s %s belonged to no agency. Nothing to detach.",
                member_kind.value,
                member_id,
            )
