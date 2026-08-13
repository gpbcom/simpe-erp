from __future__ import annotations

# Standard library imports
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from logging import Logger, getLogger
from typing import ClassVar, Dict, FrozenSet, List, Optional, Tuple

from models.auth.user import User

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.configuration.pricing_config import PricingConfig
from models.enums import QuoteStatus
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from models.quoting.quote_type_week_aggregate import QuoteTypeWeekAggregate
from models.schemas.requests.quoting.quote_create_request import QuoteCreateRequest
from models.schemas.requests.quoting.quote_filter import QuoteFilter
from service.certifications.certifications import CertificationTypeService
from service.certifications.exceptions import MTCertificationTypeUnknownCode
from service.organisation.teams import TeamService
from service.quotes.exceptions import (
    MTPricingUnknownInterventionType,
    MTQuoteForbidden,
    MTQuoteLineNotFound,
    MTQuoteNotEditable,
    MTQuoteNotFound,
    MTQuoteNotPriced,
    MTQuoteTeamForbidden,
    MTQuoteUnassignable,
)
from service.skills.exceptions import MTSkillTypeUnknownCode
from service.skills.skills import SkillTypeService
from storage.repositories.catalog.intervention_type import InterventionTypeRepository
from storage.repositories.people.customer import CustomerRepository
from storage.repositories.quoting.quote import QuoteRepository


class QuoteService:
    """Composes, prices and progresses quotes.

    Attributes:
        EDITABLE_STATUSES (ClassVar[FrozenSet[QuoteStatus]]): The statuses in
            which a quote's lines may still change.
        quotes (QuoteRepository): The quote store.
        types (InterventionTypeRepository): The catalog store.
        CENTS (ClassVar[Decimal]): The quantum every amount is rounded to.
        config (PricingConfig): The agency-wide pricing rules.
        logger (Logger): Logger for quote operations.

    Notes:
        - **A quote's lines are editable in every status.** The rule used to be
          drafts only; see :attr:`EDITABLE_STATUSES` for what that protected and
          what allowing it costs. The authorship check is unchanged — an
          assistant still edits only what they wrote — so what widened is *when*
          a quote may change, not *who* may change it.
        - Pricing is re-run whenever the lines change, and never on read. The
          stored amounts are the offer; recomputing them at display time would
          silently reprice an issued quote after its type is repriced.
    """

    EDITABLE_STATUSES: ClassVar[FrozenSet[QuoteStatus]] = frozenset(QuoteStatus)
    SENDABLE_STATUSES: ClassVar[FrozenSet[QuoteStatus]] = frozenset({QuoteStatus.DRAFT})
    VALIDITY_DAYS: ClassVar[int] = 30
    CENTS: ClassVar[Decimal] = Decimal("0.01")

    def __init__(
        self,
        quotes: QuoteRepository,
        types: InterventionTypeRepository,
        config: PricingConfig,
        teams: TeamService,
        customers: CustomerRepository,
        certifications: Optional[CertificationTypeService] = None,
        skills: Optional[SkillTypeService] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            quotes (QuoteRepository): The quote store.
            types (InterventionTypeRepository): The catalog store.
            CENTS (ClassVar[Decimal]): The quantum every amount is rounded to.
        config (PricingConfig): The agency-wide pricing rules.
            teams (TeamService): Decides which team a new quote belongs to.
            customers (CustomerRepository): Read for the household's
                coordinate, which is what "the closest team" is measured from.
            certifications (Optional[CertificationTypeService]): The
                certification catalogue, consulted before a line's requirement
                override is stored.
            skills (Optional[SkillTypeService]): The skill catalogue, consulted
                the same way and for the same reason.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.

        Notes:
            ``teams`` and ``customers`` are **required**, unlike the two
            catalogues. A quote that reached the store without a team would be
            priced, sent and then read by no planning run — so a service that
            could be built without the means to attribute one would be a service
            that can quietly write unschedulable work.
        """
        self.quotes = quotes
        self.types = types
        self.config = config
        self.teams = teams
        self.customers = customers
        self.certifications = certifications
        self.skills = skills
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("QuoteService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _assert_line_requirements_known(self, quote: Quote) -> None:
        """Refuse a line requiring a qualification the catalogue lacks.

        Args:
            quote (Quote): The quote whose lines are being stored.

        Raises:
            MTCertificationTypeUnknownCode: If a line's override names a code
                that is unknown or retired.

        Notes:
            - Only the lines that actually override are checked. A line
              inheriting its catalog entry's requirement carries ``None``, and
              that entry was already checked when it was saved — re-checking it
              here would refuse a quote because of a code that has been retired
              since, which is a change to the catalogue punishing the person
              writing an unrelated quote.
            - No catalogue wired in is only tolerable while nothing overrides.
              A requirement stored unchecked is worse than a refused write: it
              fails every planning run it touches, and the message reads as a
              staffing problem.
        """
        overridden = [
            code
            for line in quote.lines
            if line.required_certification_codes is not None
            for code in line.required_certification_codes
        ]
        if not overridden:
            return
        if self.certifications is None:
            self.logger.error(
                "Quote %s overrides its certification requirements but no "
                "certification catalogue is available to check them against.",
                quote.reference,
            )
            raise MTCertificationTypeUnknownCode(
                "Certification requirements cannot be verified; the "
                "certification catalogue is unavailable."
            )
        self.logger.debug(
            "Checking %d overridden certification code(s) on quote %s.",
            len(overridden),
            quote.reference,
        )
        await self.certifications.assert_known(overridden)

    async def _assert_line_skills_known(self, quote: Quote) -> None:
        """Refuse a line requiring a skill the catalogue lacks.

        Args:
            quote (Quote): The quote whose lines are being stored.

        Raises:
            MTSkillTypeUnknownCode: If a line's override names a code that is
                unknown or retired.

        Notes:
            The twin of :meth:`_assert_line_requirements_known`, with the same
            two rules: only the lines that actually override are checked,
            because a line inheriting its catalog entry carries ``None`` and
            that entry was checked when it was saved; and no catalogue wired in
            is tolerable only while nothing overrides.
        """
        overridden = [
            code
            for line in quote.lines
            if line.required_skill_codes is not None
            for code in line.required_skill_codes
        ]
        if not overridden:
            return
        if self.skills is None:
            self.logger.error(
                "Quote %s overrides its skill requirements but no skill "
                "catalogue is available to check them against.",
                quote.reference,
            )
            raise MTSkillTypeUnknownCode(
                "Skill requirements cannot be verified; the skill catalogue is "
                "unavailable."
            )
        self.logger.debug(
            "Checking %d overridden skill code(s) on quote %s.",
            len(overridden),
            quote.reference,
        )
        await self.skills.assert_known(overridden)

    async def _price(self, quote: Quote) -> Quote:
        """Price a quote against the catalog entries its lines name.

        Args:
            quote (Quote): The quote to price.

        Returns:
            Quote: A priced copy.

        Raises:
            MTPricingUnknownInterventionType: If a line names a missing type.

        Notes:
            The types are fetched in one query rather than one per line, so a
            twenty-line quote costs one round trip.
        """
        type_ids = [line.intervention_type_id for line in quote.lines]
        intervention_types: Dict[str, InterventionType] = await self.types.get_many(
            type_ids
        )
        return self.price_quote(quote, intervention_types)

    async def _move_to(self, quote_id: str, status: QuoteStatus) -> Quote:
        """Move a quote to a status.

        Args:
            quote_id (str): The quote to move.
            status (QuoteStatus): The status to move it to.

        Returns:
            Quote: The updated quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
        """
        updated = await self.quotes.set_status(quote_id, status)
        if updated is None:
            self.logger.warning(
                "Status change requested for absent quote %s.", quote_id
            )
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        return updated

    def _utc_now(self) -> datetime:
        """Return the current instant as timezone-aware UTC.

        Returns:
            datetime: The current instant in UTC.

        Notes:
            Read here rather than in the model, which keeps the quote free of
            ambient state and lets a test pin the clock by patching one method.
        """
        return datetime.now(UTC)

    def _to_cents(self, amount: Decimal) -> Decimal:
        """Round an exact amount to whole cents.

        Args:
            amount (Decimal): The exact amount.

        Returns:
            Decimal: The amount rounded to two decimals, half away from zero.

        Notes:
            ``ROUND_HALF_UP`` is the invoicing convention. Python's default is
            ``ROUND_HALF_EVEN``, which would send 95.715 down to 95.71 — a cent
            the customer would have to be told about.
        """
        return amount.quantize(self.CENTS, rounding=ROUND_HALF_UP)

    def _monday_of(self, iso_year: int, iso_week: int) -> date:
        """Return the Monday that starts an ISO week.

        Args:
            iso_year (int): The ISO year.
            iso_week (int): The ISO week number.

        Returns:
            date: The Monday of that week.

        Notes:
            Computed from 4 January, which ISO 8601 guarantees falls in week 1
            of its own year. Anchoring on 1 January instead would be wrong for
            every year that starts on a Friday, Saturday or Sunday, where the
            1st belongs to the last week of the previous year.
        """
        fourth_of_january = date(iso_year, 1, 4)
        week_one_monday = fourth_of_january - timedelta(
            days=fourth_of_january.isoweekday() - 1
        )
        return week_one_monday + timedelta(weeks=iso_week - 1)

    def _build(
        self,
        key: Tuple[str, int, int],
        bucket: List[QuoteLine],
        intervention_types: Dict[str, InterventionType],
    ) -> QuoteTypeWeekAggregate:
        """Build one aggregate from the lines that fell in its bucket.

        Args:
            key (Tuple[str, int, int]): The type identifier, ISO year and ISO
                week the bucket represents.
            bucket (List[QuoteLine]): The lines in that bucket.
            intervention_types (Dict[str, InterventionType]): The types behind
                the lines, keyed by identifier.

        Returns:
            QuoteTypeWeekAggregate: The totals for that type and week.

        Raises:
            KeyError: If the type is absent from the mapping.
        """
        type_id, iso_year, iso_week = key
        intervention_type = intervention_types[type_id]
        return QuoteTypeWeekAggregate(
            intervention_type_id=type_id,
            intervention_type_name=intervention_type.name,
            iso_year=iso_year,
            iso_week=iso_week,
            week_start_date=self._monday_of(iso_year, iso_week),
            line_count=len(bucket),
            total_minutes=sum(line.duration_minutes for line in bucket),
            total_ht=sum((line.total_ht for line in bucket), Decimal("0.00")),
            vat_amount=sum((line.vat_amount for line in bucket), Decimal("0.00")),  # noqa: E501
            total_ttc=sum((line.total_ttc for line in bucket), Decimal("0.00")),  # noqa: E501
        )

    async def _renew(self, parent: Quote, today: date) -> Quote:
        """Write one successor to an expired quote.

        Args:
            parent (Quote): The quote being succeeded.
            today (date): The day the renewal runs.

        Returns:
            Quote: The stored successor.

        Notes:
            - The shift is the parent's own span — first service to last — plus
              a day, so a four-week arrangement renews into the four weeks that
              follow rather than overlapping itself.
            - The successor **inherits the parent's team** rather than being
              re-attributed. The household has not moved and the arrangement has
              not changed; re-running the rule would hand a continuing customer
              to whichever team happened to be least busy that morning, and the
              assistants they already know would stop coming.
        """
        days = [line.service_date for line in parent.lines]
        span = (max(days) - min(days)).days + 1 if days else self.VALIDITY_DAYS
        shift = timedelta(days=span)

        successor = Quote(
            reference=f"{parent.reference}-R{today:%Y%m}",
            company_id=parent.company_id,
            team_id=parent.team_id,
            customer_id=parent.customer_id,
            status=parent.status,
            authored_by=parent.authored_by,
            auto_renew=True,
            renewed_from_id=parent.id,
            lines=[
                line.model_copy(
                    update={
                        "id": None,
                        "service_date": line.service_date + shift,
                        "hourly_rate_ht": None,
                        "total_ht": None,
                        "vat_amount": None,
                        "total_ttc": None,
                    }
                )
                for line in parent.lines
            ],
        )
        catalog = await self.types.get_many(
            [line.intervention_type_id for line in successor.lines]
        )
        priced = self.price_quote(successor, catalog)
        issued = today
        stored = await self.quotes.create(
            priced.model_copy(
                update={
                    "issued_on": issued,
                    "valid_until": issued + timedelta(days=self.VALIDITY_DAYS),
                }
            )
        )
        self.logger.info(
            "Quote %s renewed as %s, covering %s onward at %s TTC.",
            parent.reference,
            stored.reference,
            min(line.service_date for line in stored.lines) if stored.lines else "—",  # noqa: E501
            stored.total_ttc(),
        )
        return stored

    async def _attribute(self, company_id: str, customer_id: str) -> str:
        """Return the team a new quote for this household belongs to.

        Args:
            company_id (str): The company writing the quote.
            customer_id (str): The household it is addressed to.

        Returns:
            str: The chosen team's identifier.

        Raises:
            MTQuoteUnassignable: If the household is unknown, or the company has
                no team to give the work to.

        Notes:
            - **The rule itself is not here.** Nearest site, then fewest
              assigned minutes, then first by identifier lives in
              :meth:`~service.organisation.teams.TeamService.attribute`. What is
              here is the refusal, because only the quote knows that failing to
              choose means the quote cannot exist.
            - The two causes carry **different messages**, deliberately. One is
              fixed by correcting a household's address and the other by forming
              a team; a single "could not be assigned" sends somebody to look
              for both.
            - A household with no resolved coordinate is **not** refused here.
              It falls through to the busyness tie-break, which is the honest
              answer: the quote is filed with the least loaded team and the
              WARNING in ``attribute`` says no distance was measured. Refusing
              would make a geocoding outage stop the business taking work.
        """
        customer = await self.customers.get(customer_id)
        if customer is None:
            self.logger.warning(
                "Quote refused: customer %s does not exist.", customer_id
            )
            raise MTQuoteUnassignable(
                f"No customer {customer_id!r} exists, so no team can be given "
                f"this work."
            )
        team_id = await self.teams.attribute(company_id, customer)
        if team_id is None:
            self.logger.error(
                "Quote refused: company %s could attribute no team to customer %s.",
                company_id,
                customer_id,
            )
            raise MTQuoteUnassignable(
                "No team could be given this work. Either this company has no "
                "team yet, or none of its teams has anybody on it. Form a team "
                "at the site nearest the household first."
            )
        self.logger.debug("Customer %s is attributed to team %s.", customer_id, team_id)
        return team_id

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(
        self,
        payload: QuoteCreateRequest,
        company_id: str,
        author_id: Optional[str] = None,
    ) -> Quote:
        """Create a quote, attribute it to a team and price its lines.

        Args:
            payload (QuoteCreateRequest): What the caller asked for.
            company_id (str): The agency the quote belongs to, taken from the
                caller's credential.
            author_id (Optional[str]): The account writing it, recorded as the
                author. ``None`` leaves the quote unattributed to anybody.

        Returns:
            Quote: The stored, priced quote.

        Raises:
            MTQuoteUnassignable: If no team can be given the work; 422.
            MTPricingUnknownInterventionType: If a line names a missing type.
            MTCertificationTypeUnknownCode: If a line requires a qualification
                the certification catalogue does not offer.
            MTSkillTypeUnknownCode: If a line requires a skill the skill
                catalogue does not offer.

        Notes:
            - **This takes the payload rather than a built quote, and that is
              the whole point of the change.** Both writing paths — a manager at
              ``POST /api/v1/quotes`` and an assistant at
              ``POST /api/v1/me/quotes`` — arrive here, so the attribution rule
              is written once. Had the routes built the quote, each would have
              needed the team service, and the assistant's path is the one that
              would have been forgotten.
            - The company and the author are taken from the caller's own
              credential, never from the payload. A quote naming somebody else
              as its author would land in their list, and they would be the one
              a manager asks about a price they never set.
            - The team is resolved **before** the lines are validated or priced.
              Both orders give the same answer; this one means a company with no
              team is told so instead of being told about a missing catalogue
              entry on a quote it could never have filed.
        """
        self.logger.info(
            "Creating quote %s for customer %s, authored by %s.",
            payload.reference,
            payload.customer_id,
            author_id,
        )
        team_id = await self._attribute(company_id, payload.customer_id)
        quote = payload.to_quote(company_id, team_id)
        await self._assert_line_requirements_known(quote)
        await self._assert_line_skills_known(quote)
        priced = await self._price(quote)
        if author_id is not None:
            priced = priced.model_copy(update={"authored_by": author_id})
        return await self.quotes.create(priced)

    async def reassign_team(self, quote_id: str, team_id: str, caller: User) -> Quote:  # noqa: E501
        """Move a quote to a different team.

        Args:
            quote_id (str): The quote to move.
            team_id (str): The team that will deliver it instead.
            caller (User): The manager or administrator moving it.

        Returns:
            Quote: The stored quote, now naming the new team.

        Raises:
            MTQuoteNotFound: If no such quote exists, or it belongs to another
                company; answered as a 404.
            MTQuoteTeamForbidden: If the caller may read neither the team the
                quote leaves nor the one it joins; answered as a 403.

        Notes:
            - **Explicit rather than automatic.** Attribution runs once, when
              the quote is written. Re-running it whenever a household moved or
              a team's load changed would silently move work a manager has
              already validated, and with it visits somebody has been told
              about.
            - Both ends are checked. Moving work *out* of a team the caller does
              not run takes it off a colleague's plan; moving it *into* one
              commits assistants the caller does not manage. An administrator
              passes both because they read every team.
            - The visits already planned are **not** moved. They belong to a run
              that has been carried out, and rewriting history is not what this
              is for — the next run of each team picks the change up, which is
              why the caller is told to re-plan both.
        """
        quote = await self.get(quote_id)
        if quote.company_id != caller.company_id:
            self.logger.warning(
                "Account %s cannot move quote %s of company %s.",
                caller.id,
                quote_id,
                quote.company_id,
            )
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        readable = await self.teams.readable_team_ids(caller)
        if readable is not None and (
            quote.team_id not in readable or team_id not in readable
        ):
            self.logger.warning(
                "Account %s may not move quote %s from team %s to team %s.",
                caller.id,
                quote_id,
                quote.team_id,
                team_id,
            )
            raise MTQuoteTeamForbidden(
                "A quote may only be moved between teams you run."
            )
        await self.teams.get(team_id, caller)
        self.logger.info(
            "Moving quote %s from team %s to team %s, requested by %s; both "
            "teams need re-planning.",
            quote_id,
            quote.team_id,
            team_id,
            caller.id,
        )
        stored = await self.quotes.update(quote.model_copy(update={"team_id": team_id}))
        if stored is None:
            self.logger.error("Quote %s vanished while being moved.", quote_id)
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        return stored

    async def get(self, quote_id: str) -> Quote:
        """Return a quote by identifier.

        Args:
            quote_id (str): The identifier to look up.

        Returns:
            Quote: The quote, with its lines and weekly totals.

        Raises:
            MTQuoteNotFound: If no such quote exists.
        """
        found = await self.quotes.get(quote_id)
        if found is None:
            self.logger.warning("Quote %s does not exist.", quote_id)
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        return found

    async def get_by_line(self, line_id: str) -> Quote:
        """Return the quote one line belongs to.

        Args:
            line_id (str): The line to look the quote up by.

        Returns:
            Quote: The whole quote, with its lines and weekly totals.

        Raises:
            MTQuoteNotFound: If no quote carries that line.

        Notes:
            For the callers that hold a line and not a quote — a scheduled
            visit knows which line produced it and nothing else about the
            paperwork. Editing the visit has to reach the quote, or the
            calendar and the bill drift apart.
        """
        found = await self.quotes.get_by_line(line_id)
        if found is None:
            self.logger.warning("No quote carries a line %s.", line_id)
            raise MTQuoteNotFound(f"No quote carries a line {line_id!r}.")
        return found

    async def delete(self, quote_id: str) -> None:
        """Remove a quote and its lines.

        Args:
            quote_id (str): The quote to remove.

        Raises:
            MTQuoteNotFound: If no such quote exists.

        Notes:
            - Deletion is **not** part of a quote's lifecycle: a quote that a
              customer refused is rejected, not erased, because the agency has
              to be able to say what it offered and when. This exists for the
              records that were never part of that history — a quote raised in
              error, and the fixtures a test campaign creates and is obliged to
              remove again.
            - Absence is reported rather than passed over. A caller deleting a
              quote it believes it created wants to know when there was nothing
              there; a silent success hides a fixture that was never made, or
              one already removed by something else.
        """
        removed = await self.quotes.delete(quote_id)
        if not removed:
            self.logger.warning("Quote %s does not exist; nothing deleted.", quote_id)  # noqa: E501
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        self.logger.info("Deleted quote %s.", quote_id)

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        customer_id: Optional[str] = None,
        status: Optional[QuoteStatus] = None,
        authored_by: Optional[str] = None,
        quote_filter: Optional[QuoteFilter] = None,
        team_ids: Optional[List[str]] = None,
    ) -> List[Quote]:
        """Return a page of quotes.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            customer_id (Optional[str]): Restrict to one customer.
            status (Optional[QuoteStatus]): Restrict to one status.
            authored_by (Optional[str]): Restrict to one author's quotes.
            quote_filter (Optional[QuoteFilter]): The screen's filter.
            team_ids (Optional[List[str]]): The teams the caller may read.
                ``None`` means every team; an empty list means none.

        Returns:
            List[Quote]: The matching quotes.

        Notes:
            ``authored_by`` and ``team_ids`` are both passed separately from the
            filter and stay separate all the way down. They are the caller's
            *scope* rather than their preference, and the store is what refuses
            to let the filter widen either.
        """
        return await self.quotes.list(
            page=page,
            size=size,
            customer_id=customer_id,
            status=status,
            authored_by=authored_by,
            quote_filter=quote_filter,
            team_ids=team_ids,
        )

    async def list_for(
        self,
        caller: User,
        page: int = 1,
        size: Optional[int] = None,
        customer_id: Optional[str] = None,
        status: Optional[QuoteStatus] = None,
        quote_filter: Optional[QuoteFilter] = None,
    ) -> List[Quote]:
        """Return the quotes a caller is allowed to see.

        Args:
            caller (User): The authenticated caller.
            page (int): One-based page number.
            size (Optional[int]): Page size.
            customer_id (Optional[str]): Restrict to one customer.
            status (Optional[QuoteStatus]): Restrict to one status.
            quote_filter (Optional[QuoteFilter]): The screen's filter.

        Returns:
            List[Quote]: The matching quotes of the teams they may read.

        Notes:
            - **The narrowing is resolved here and applied in the statement**,
              never by filtering the page afterwards. A page of fifty cut down
              to three has already read forty-seven quotes the caller may not
              see, which is the rule ``docs/11-security.md`` states and the
              reason this method exists beside :meth:`list`.
            - An administrator's ``None`` and a manager-with-no-team's ``[]``
              travel unchanged to the store, which knows the difference.
        """
        team_ids = await self.teams.readable_team_ids(caller)
        self.logger.debug(
            "Listing quotes for %s, narrowed to %s.",
            caller.id,
            "every team" if team_ids is None else f"{len(team_ids)} team(s)",
        )
        return await self.list(
            page=page,
            size=size,
            customer_id=customer_id,
            status=status,
            quote_filter=quote_filter,
            team_ids=team_ids,
        )

    async def replace_lines(
        self,
        quote_id: str,
        lines: List[QuoteLine],
        author_id: Optional[str] = None,
    ) -> Quote:
        """Replace a draft quote's lines and reprice it.

        Args:
            quote_id (str): The quote to change.
            lines (List[QuoteLine]): The services that replace the stored ones.
            author_id (Optional[str]): When given, the caller must be the
                quote's author. ``None`` skips the check, for a manager who may
                edit any quote in their agency.

        Returns:
            Quote: The stored, repriced quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteForbidden: If ``author_id`` is given and did not write it.
            MTQuoteNotEditable: If the quote is past draft.
            MTPricingUnknownInterventionType: If a line names a missing type.
            MTCertificationTypeUnknownCode: If a line requires a qualification
                the certification catalogue does not offer.
            MTSkillTypeUnknownCode: If a line requires a skill the skill
                catalogue does not offer.

        Notes:
            - **Only the lines can be given, rather than only the lines being
              read.** This took a whole quote and used one field of it, which
              meant the promise that a reference, a customer or a status could
              not be changed here rested on this method remembering not to look.
              Taking the lines themselves makes it a property of the signature —
              and it had to become one once a quote carried its agency, since a
              body able to name one would let a repricing move a quote between
              agencies.
            - **The authorship check is a parameter rather than a second
              method.** A manager may edit any quote and an assistant only
              their own, but everything after that decision — the draft check,
              the repricing, the write — is identical, and two copies of it
              would be two places for the pricing rules to drift apart. The
              route decides who is asking; this decides what happens next.
        """
        existing = await self.get(quote_id)
        if author_id is not None and existing.authored_by != author_id:
            self.logger.warning(
                "Account %s tried to edit quote %s, written by %s.",
                author_id,
                existing.reference,
                existing.authored_by,
            )
            raise MTQuoteForbidden("You may only edit a quote you wrote.")
        if existing.status not in self.EDITABLE_STATUSES:
            self.logger.warning(
                "Refused to edit quote %s: it is %s, not a draft.",
                existing.reference,
                existing.status.value,
            )
            raise MTQuoteNotEditable(
                f"Quote {existing.reference!r} is {existing.status.value} and "
                f"cannot be edited."
            )
        self.logger.info(
            "Replacing the %d line(s) of quote %s with %d new one(s).",
            len(existing.lines),
            existing.reference,
            len(lines),
        )
        edited = existing.model_copy(update={"lines": list(lines)})
        await self._assert_line_requirements_known(edited)
        await self._assert_line_skills_known(edited)
        priced = await self._price(edited)
        updated = await self.quotes.update(priced)
        if updated is None:
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        return updated

    async def reschedule_line(
        self,
        quote_id: str,
        quote_line_id: str,
        day: date,
        start_minute: int,
        end_minute: int,
    ) -> Quote:
        """Move one line onto a time the planner offered, and reprice.

        Args:
            quote_id (str): The quote to change.
            quote_line_id (str): The line to move.
            day (date): The day the work should happen on instead.
            start_minute (int): Earliest it may begin, in minutes from midnight.
            end_minute (int): Latest it may finish, in the same units.

        Returns:
            Quote: The stored, repriced quote, with its planning note cleared.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteLineNotFound: If the quote does not carry that line.
            MTQuoteLineWindowTooShort: If the offered window is narrower than
                the work takes; answered as a 422.
            MTPricingUnknownInterventionType: If the line names a missing type.

        Notes:
            - **The status is deliberately untouched.** The quote came back to
              be validated because its work would not fit; accepting a new time
              answers *when*, not *whether*, so it stays in the queue for
              somebody to validate. Moving it on here would let a scheduling
              tweak approve work nobody agreed to.
            - **It reprices.** A visit moved from a Tuesday to a Sunday, or onto
              a public holiday, costs more — the surcharge is a property of the
              day. Leaving the old total would print a document whose figures
              do not follow from its own dates.
            - **The planning note is cleared.** Its reasons describe a date that
              has just changed and its offers were computed against a plan that
              no longer applies; leaving them on screen invites a second click
              that silently overwrites the first. The next run re-attaches a
              fresh one if the work still does not fit.
            - No assistant is recorded. A quote says what is sold and when, not
              who does it — the planner assigns that, and a preference stored
              here would be a promise nothing keeps.
        """
        existing = await self.get(quote_id)
        line = next((item for item in existing.lines if item.id == quote_line_id), None)
        if line is None:
            self.logger.warning(
                "Quote %s carries no line %s to reschedule; the offer was "
                "probably computed before the quote was last edited.",
                existing.reference,
                quote_line_id,
            )
            raise MTQuoteLineNotFound(
                f"Quote {existing.reference!r} has no line {quote_line_id!r}."
            )
        self.logger.info(
            "Moving line %s of quote %s from %s to %s %02d:%02d-%02d:%02d.",
            quote_line_id,
            existing.reference,
            line.service_date,
            day,
            start_minute // 60,
            start_minute % 60,
            end_minute // 60,
            end_minute % 60,
        )
        moved = line.model_copy(
            update={
                "service_date": day,
                "earliest_start": time(start_minute // 60, start_minute % 60),
                "latest_end": time(end_minute // 60, end_minute % 60),
            }
        )
        # Rebuilt rather than mutated, so the window check runs: a slot narrower
        # than the work takes must be refused here rather than stored and left
        # to fail every planning run afterwards.
        moved = QuoteLine.model_validate(moved.model_dump())
        edited = existing.model_copy(
            update={
                "lines": [
                    moved if item.id == quote_line_id else item
                    for item in existing.lines
                ],
                "planning_feedback": None,
            }
        )
        priced = await self._price(edited)
        updated = await self.quotes.update(priced)
        if updated is None:
            self.logger.error(
                "Quote %s vanished while its line was being rescheduled.",
                existing.reference,
            )
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        self.logger.debug(
            "Quote %s rescheduled and still %s.",
            updated.reference,
            updated.status.value,
        )
        return updated

    async def update_header(
        self,
        quote_id: str,
        reference: str,
        customer_id: str,
        issued_on: Optional[date],
        valid_until: Optional[date],
        auto_renew: bool,
    ) -> Quote:
        """Change everything about a quote except its lines and its status.

        Args:
            quote_id (str): The quote to change.
            reference (str): The human-facing quote number.
            customer_id (str): Who the offer is addressed to.
            issued_on (Optional[date]): When it was issued.
            valid_until (Optional[date]): The last day it may be accepted.
            auto_renew (bool): Whether it renews itself.

        Returns:
            Quote: The updated quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.

        Notes:
            - **The planning note is cleared.** A quote carries the reason its
              work would not fit and the times that were free instead; the
              moment somebody edits it, that note describes a quote which no
              longer exists. Leaving it would send the next reader to
              renegotiate a date that has already been changed.
            - Reassigning the customer is logged at WARNING rather than
              refused. It moves every visit on the quote to a different
              address, which is occasionally exactly right — a quote written
              against the wrong record — and never something to do without
              leaving a trace.
            - Not repriced. The amounts follow the lines, and the lines are not
              touched here; a header edit that silently moved the total would
              change what a customer owes because somebody corrected a date.
        """
        existing = await self.get(quote_id)
        if existing.customer_id != customer_id:
            self.logger.warning(
                "Quote %s is reassigned from customer %s to %s; every visit "
                "on it moves to a different address.",
                existing.reference,
                existing.customer_id,
                customer_id,
            )
        if existing.reference != reference:
            self.logger.info(
                "Quote %s is renumbered to %s.", existing.reference, reference
            )
        self.logger.debug("Updating the header of quote %s.", existing.reference)
        edited = existing.model_copy(
            update={
                "reference": reference,
                "customer_id": customer_id,
                "issued_on": issued_on,
                "valid_until": valid_until,
                "auto_renew": auto_renew,
                "planning_feedback": None,
            }
        )
        updated = await self.quotes.update(edited)
        if updated is None:
            self.logger.error(
                "Quote %s vanished while its header was being updated.", quote_id
            )
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        self.logger.info("Quote %s header updated.", updated.reference)
        return updated

    async def reprice(self, quote_id: str) -> Quote:
        """Recompute a draft quote's amounts against the current catalog.

        Args:
            quote_id (str): The quote to reprice.

        Returns:
            Quote: The stored, repriced quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteNotEditable: If the quote is past draft.

        Notes:
            Allowed in every status, like editing. What that costs is that an
            issued quote no longer necessarily carries the figures the customer
            was shown: repricing runs against the catalogue as it stands now.
        """
        existing = await self.get(quote_id)
        if existing.status not in self.EDITABLE_STATUSES:
            raise MTQuoteNotEditable(
                f"Quote {existing.reference!r} is {existing.status.value} and "
                f"cannot be repriced. Its figures are what the customer saw."
            )
        self.logger.info("Repricing quote %s.", existing.reference)
        updated = await self.quotes.update(await self._price(existing))
        if updated is None:
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        return updated

    async def interrupt(self, quote_id: str, last_day: date) -> Quote:
        """Give a running arrangement a last day, and reprice it.

        Args:
            quote_id (str): The quote to end.
            last_day (date): The final day the arrangement is delivered.

        Returns:
            Quote: The shortened, repriced quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteInvalidInterruption: If the day falls before the quote was
                issued or before its first service.
            MTPricingUnknownInterventionType: If a line names a type the
                catalog no longer has.

        Notes:
            - **The lines are kept and the total shrinks.** Deleting the
              cancelled visits would leave nothing to answer a family asking why
              the invoice came in under the quote they signed. They stay on the
              record, priced, and stop counting towards the total — which is what
              :meth:`~models.quoting.quote.Quote.effective_lines` decides and
              what the aggregates are then built from.
            - **Repricing happens here rather than at read time.** An issued
              quote must reprint identically, so amounts are stored; a total
              recomputed on every read would drift the first time the catalog
              changed. Interrupting is the deliberate act that makes a new total
              correct, so it is the moment to write one.
            - **The day is inclusive:** work on ``last_day`` still happens. A family
              cancelling "from the 15th" means the 15th is the last visit.
        """
        self.logger.info("Interrupting quote %s on %s.", quote_id, last_day)
        quote = await self.get(quote_id)
        shortened = quote.model_copy(update={"interrupted_on": last_day})

        catalog = await self.types.get_many(
            [line.intervention_type_id for line in shortened.lines]
        )
        repriced = self.price_quote(shortened, catalog)
        dropped = len(repriced.lines) - len(repriced.effective_lines())
        self.logger.info(
            "Quote %s now ends on %s: %d line(s) dropped, total is %s TTC.",
            quote.reference,
            last_day,
            dropped,
            repriced.total_ttc(),
        )
        updated = await self.quotes.update(repriced)
        if updated is None:
            self.logger.error(
                "Quote %s vanished while being interrupted.", quote_id
            )  # noq
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        return updated

    async def set_auto_renew(self, quote_id: str, enabled: bool) -> Quote:
        """Record whether a quote writes a successor when it expires.

        Args:
            quote_id (str): The quote to change.
            enabled (bool): Whether renewal is wanted.

        Returns:
            Quote: The updated quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.

        Notes:
            A flag rather than an immediate act: nothing is renewed until the
            quote actually reaches its validity date, so turning this on and
            off again before then costs nothing.
        """
        self.logger.info("Setting auto-renewal on quote %s to %s.", quote_id, enabled)  # noqa: E501
        quote = await self.get(quote_id)
        updated = await self.quotes.update(
            quote.model_copy(update={"auto_renew": enabled})
        )
        if updated is None:
            self.logger.error("Quote %s vanished while setting auto-renewal.", quote_id)  # noqa: E501
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        return updated

    async def renew_due(self, today: Optional[date] = None) -> List[Quote]:
        """Write successors for the arrangements that have expired.

        Args:
            today (Optional[date]): The day to treat as now; defaults to today.

        Returns:
            List[Quote]: The successor quotes created, newest last.

        Notes:
            - **A successor is a new quote, not an extended one.** Extending
              ``valid_until`` in place would rewrite what the customer accepted
              and lose the boundary between one period and the next — and the
              price. A renewal is priced at the catalog as it stands now, so a
              rate change reaches the next period rather than the one already
              agreed.
            - **Idempotent, and that is the whole design.** ``renewed_from_id``
              records the parent, and a quote that already has a successor is
              skipped — so running the sweep twice in a day, or twice because two
              workers woke up together, creates one successor and not two. Nothing
              else would be safe to put on a timer.
            - The successor's services are the parent's, shifted forward by the
              length of the period it covered, so a weekly arrangement stays on
              the same weekdays. An interrupted quote is never renewed: an end
              date is the customer saying stop.
        """
        today = today or self._utc_now().date()
        self.logger.info("Looking for arrangements to renew as of %s.", today)
        candidates = await self.quotes.list_renewable(today)

        renewed: List[Quote] = []
        for parent in candidates:
            if parent.is_interrupted():
                self.logger.info(
                    "Quote %s ended on %s; not renewing it.",
                    parent.reference,
                    parent.interrupted_on,
                )
                continue
            if await self.quotes.has_successor(parent.id or ""):
                self.logger.debug(
                    "Quote %s has already been renewed; skipping.",
                    parent.reference,  # noqa: E501
                )
                continue
            renewed.append(await self._renew(parent, today))

        self.logger.info("Renewed %d arrangement(s).", len(renewed))
        return renewed

    async def send(self, quote_id: str, validator_id: str) -> Quote:
        """Issue a priced draft to the customer, agreed as it goes out.

        Args:
            quote_id (str): The quote to send.
            validator_id (str): The manager sending it, recorded as the account
                that agreed to the figures.

        Returns:
            Quote: The issued quote, accepted and schedulable.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteNotPriced: If the quote has no priced lines.
            MTQuoteNotEditable: If the quote is past draft.

        Notes:
            - **Sending lands the quote in ``ACCEPTED``, not ``SENT``.** A quote
              written by hand is one a manager has already settled with the
              family, and the manual route had no second step: nothing in the
              agency ever moved a quote past ``SENT``, so a hand-written
              arrangement sat outside :attr:`Quote.SCHEDULABLE_STATUSES` and the
              planner never saw the visits somebody had already promised.
            - Sending it *is* the approval, so the sender is recorded as the
              validator and the offer gets its dates here — an issued quote with
              no issue date and no expiry is one a customer can hold the agency
              to for ever.
            - **The assistant's route is untouched.** A quote they write still
              waits at ``PENDING_VALIDATION``, reaches ``SENT`` when a manager
              approves it, and is accepted separately when the family answers —
              there, the agency genuinely does not yet know the answer.
            - An unpriced or empty quote cannot be sent. Both would reach the
              customer as an offer of nothing for nothing.
        """
        existing = await self.get(quote_id)
        if not existing.is_priced():
            self.logger.warning(
                "Refused to send quote %s: it has no priced lines.",
                existing.reference,
            )
            raise MTQuoteNotPriced(
                f"Quote {existing.reference!r} has no priced lines and cannot be sent."
            )
        if existing.status not in self.SENDABLE_STATUSES:
            self.logger.warning(
                "Refused to send quote %s: it is %s.",
                existing.reference,
                existing.status.value,
            )
            raise MTQuoteNotEditable(
                f"Quote {existing.reference!r} is {existing.status.value} and "
                f"cannot be sent."
            )
        issued_on = self._utc_now().date()
        self.logger.debug(
            "Issuing quote %s on %s, valid for %d day(s).",
            existing.reference,
            issued_on,
            self.VALIDITY_DAYS,
        )
        sent = await self.quotes.record_validation(
            quote_id,
            status=QuoteStatus.ACCEPTED,
            validated_by=validator_id,
            validated_at=self._utc_now(),
            issued_on=issued_on,
            valid_until=issued_on + timedelta(days=self.VALIDITY_DAYS),
        )
        if sent is None:
            self.logger.error(
                "Quote %s vanished between the checks and the write.", quote_id
            )
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        self.logger.info(
            "Quote %s was sent to the customer by %s and agreed on the spot: "
            "%d line(s) are now schedulable.",
            sent.reference,
            validator_id,
            len(sent.effective_lines()),
        )
        return sent

    async def submit_for_validation(self, quote_id: str, author_id: str) -> Quote:  # noqa: E501
        """Put an assistant's draft in front of a manager.

        Args:
            quote_id (str): The quote to submit.
            author_id (str): The account submitting it.

        Returns:
            Quote: The submitted quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteNotPriced: If the quote has no priced lines.
            MTQuoteNotEditable: If the quote is not a draft.
            MTQuoteForbidden: If the caller did not write it.

        Notes:
            **The authorship check is here, not in the endpoint.** A route guard
            proves the caller is an assistant; it cannot stop assistant A
            submitting assistant B's draft, and only a comparison against the
            stored author can. A manager is allowed through: they own every
            quote in the agency, and refusing them their own draft would be
            gratuitous.
        """
        existing = await self.get(quote_id)
        if existing.authored_by is not None and existing.authored_by != author_id:
            self.logger.warning(
                "Account %s tried to submit quote %s, written by %s.",
                author_id,
                existing.reference,
                existing.authored_by,
            )
            raise MTQuoteForbidden("You may only submit a quote you wrote.")
        if not existing.status.is_editable():
            self.logger.warning(
                "Refused to submit quote %s: it is %s, not a draft.",
                existing.reference,
                existing.status.value,
            )
            raise MTQuoteNotEditable(
                f"Quote {existing.reference!r} is {existing.status.value} and "
                f"cannot be submitted for validation."
            )
        if not existing.is_priced():
            self.logger.warning(
                "Refused to submit quote %s: it has no priced lines.",
                existing.reference,
            )
            raise MTQuoteNotPriced(
                f"Quote {existing.reference!r} has no priced lines and cannot "
                f"be submitted for validation."
            )
        submitted = await self.quotes.record_submission(quote_id, self._utc_now())  # noqa: E501
        if submitted is None:
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        self.logger.info(
            "Quote %s is awaiting validation, submitted by %s.",
            submitted.reference,
            author_id,
        )
        return submitted

    async def validate(self, quote_id: str, validator_id: str) -> Quote:
        """Approve a submitted quote, making it sendable.

        Args:
            quote_id (str): The quote to validate.
            validator_id (str): The manager ruling on it.

        Returns:
            Quote: The validated quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteNotEditable: If the quote is not awaiting validation.
            MTQuoteNotPriced: If the quote has no priced lines.

        Notes:
            - **Validation moves the quote to ``ACCEPTED``**, which is the one
              status the planner loads. The manager's approval *is* the
              commitment here: an assistant writes up an arrangement they have
              already settled with the family, so by the time it reaches the
              validation queue the customer has agreed and what is being ruled
              on is the agency's figures. This is the same reasoning
              :meth:`send` applies to a manager's own hand-written quote, and
              the two paths now end in the same place.
            - It used to stop at ``SENT``, which read as an offer awaiting an
              answer and needed a second, separate acceptance before any of the
              work was scheduled. Nothing said so: the quote left the
              validation queue, the run was re-run, and the same visit count
              came back. A step that exists but is invisible is a step that
              does not happen.
            - ``SENT`` is no longer produced by any path. It is kept on
              :class:`~models.enums.QuoteStatus` — and its tab and buttons are
              kept in the interface — because quotes already stored in it need
              somewhere to be seen and a way to be moved on.
            - Sending it back to ``DRAFT`` instead was the obvious alternative
              and is wrong — an approved quote would then be indistinguishable
              from one nobody had looked at, and the assistant could edit the
              figures a manager had just signed off.
        """
        existing = await self.get(quote_id)
        if not existing.status.is_awaiting_validation():
            self.logger.warning(
                "Refused to validate quote %s: it is %s.",
                existing.reference,
                existing.status.value,
            )
            raise MTQuoteNotEditable(
                f"Quote {existing.reference!r} is {existing.status.value} and "
                f"is not awaiting validation."
            )
        if not existing.is_priced():
            raise MTQuoteNotPriced(
                f"Quote {existing.reference!r} has no priced lines and cannot "
                f"be validated."
            )
        issued_on = self._utc_now().date()
        validated = await self.quotes.record_validation(
            quote_id,
            status=QuoteStatus.ACCEPTED,
            validated_by=validator_id,
            validated_at=self._utc_now(),
            issued_on=issued_on,
            valid_until=issued_on + timedelta(days=self.VALIDITY_DAYS),
        )
        if validated is None:
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        self.logger.info(
            "Quote %s validated by %s; its %d line(s) are now schedulable.",
            validated.reference,
            validator_id,
            len(validated.lines),
        )
        return validated

    async def refuse_validation(self, quote_id: str, validator_id: str) -> Quote:  # noqa: E501
        """Send a submitted quote back to its author.

        Args:
            quote_id (str): The quote to send back.
            validator_id (str): The manager ruling on it.

        Returns:
            Quote: The quote, back in draft.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteNotEditable: If the quote is not awaiting validation.

        Notes:
            Refusal returns the quote to ``DRAFT`` rather than to ``REJECTED``.
            ``REJECTED`` means *the customer said no*, and collapsing the two
            would lose the difference between an offer the agency declined to
            make and one the family turned down — which are opposite facts about
            the same customer. Back in draft, the assistant can fix the figures
            and submit again.
        """
        existing = await self.get(quote_id)
        if not existing.status.is_awaiting_validation():
            self.logger.warning(
                "Refused to rule on quote %s: it is %s.",
                existing.reference,
                existing.status.value,
            )
            raise MTQuoteNotEditable(
                f"Quote {existing.reference!r} is {existing.status.value} and "
                f"is not awaiting validation."
            )
        returned = await self.quotes.record_validation(
            quote_id,
            status=QuoteStatus.DRAFT,
            validated_by=validator_id,
            validated_at=self._utc_now(),
        )
        if returned is None:
            raise MTQuoteNotFound(f"No quote {quote_id!r} exists.")
        self.logger.warning(
            "Quote %s was sent back to its author by %s.",
            returned.reference,
            validator_id,
        )
        return returned

    async def accept(self, quote_id: str) -> Quote:
        """Record a customer's acceptance.

        Args:
            quote_id (str): The quote to accept.

        Returns:
            Quote: The updated quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
            MTQuoteNotPriced: If the quote has no priced lines.

        Notes:
            Acceptance is what makes a quote's lines schedulable, so this is
            the moment work is committed to. The priced check is repeated here
            rather than assumed from :meth:`send`, because a quote can reach
            acceptance without passing through this service.
        """
        existing = await self.get(quote_id)
        if not existing.is_priced():
            raise MTQuoteNotPriced(
                f"Quote {existing.reference!r} has no priced lines and cannot "
                f"be accepted."
            )
        self.logger.info(
            "Quote %s accepted: %d line(s) are now schedulable.",
            existing.reference,
            len(existing.lines),
        )
        return await self._move_to(quote_id, QuoteStatus.ACCEPTED)

    async def reject(self, quote_id: str) -> Quote:
        """Record a customer's refusal.

        Args:
            quote_id (str): The quote to reject.

        Returns:
            Quote: The updated quote.

        Raises:
            MTQuoteNotFound: If no such quote exists.
        """
        return await self._move_to(quote_id, QuoteStatus.REJECTED)

    def base_rate_for(self, intervention_type: InterventionType) -> Decimal:
        """Return the hourly rate a type bills at, before any surcharge.

        Args:
            intervention_type (InterventionType): The type being billed.

        Returns:
            Decimal: The type's own rate, or the agency default.
        """
        resolved = intervention_type.effective_hourly_rate_ht(
            self.config.base_hourly_rate_ht
        )
        if intervention_type.base_hourly_rate_ht is None:
            self.logger.debug(
                "Type %s bills the agency default of %s.",
                intervention_type.code,
                resolved,
            )
        else:
            self.logger.debug(
                "Type %s bills its own rate of %s.",
                intervention_type.code,
                resolved,  # noqa: E501
            )
        return resolved

    def multiplier_for(self, service_date: date) -> Decimal:
        """Return the multiplier applying to a service date.

        Args:
            service_date (date): The day the service is delivered.

        Returns:
            Decimal: ``1`` on an ordinary day, ``1.25`` on a surcharged
            Sunday, ``1.50`` on Christmas Day or New Year's Day.
        """
        multiplier = self.config.multiplier_for(service_date)
        if multiplier != Decimal("1"):
            self.logger.info(
                "%s carries a surcharge: billing at x%s.",
                service_date,
                multiplier,  # noqa: E501
            )
        else:
            self.logger.debug("%s carries no surcharge.", service_date)
        return multiplier

    def vat_rate_for(self, line: QuoteLine) -> Decimal:
        """Return the VAT rate a quote line is taxed at.

        Args:
            line (QuoteLine): The line being billed.

        Returns:
            Decimal: ``0.055`` for necessity care, ``0.20`` for comfort care.

        Notes:
            - **Read from the line, not from the catalog entry it sells.** The
              same service is necessity care for one customer and comfort care
              for another — help with washing under a care plan is billed at the
              reduced rate, and the same hour arranged privately is not. Which it
              is depends on the customer, so it cannot be a property of the
              service; it is chosen when the quote is written, by the person who
              knows.
            - The catalog still fixes the *rate*. It no longer fixes the tax.
        """
        rate = line.service_category.vat_rate()
        self.logger.debug(
            "Line %r is %s care, taxed at %s.",
            line.name,
            line.service_category.value,
            rate,
        )
        return rate

    def aggregate(
        self,
        lines: List[QuoteLine],
        intervention_types: Dict[str, InterventionType],
    ) -> List[QuoteTypeWeekAggregate]:
        """Group priced lines into per-type, per-week totals.

        Args:
            lines (List[QuoteLine]): The priced lines to summarise.
            intervention_types (Dict[str, InterventionType]): The types behind
                those lines, keyed by identifier.

        Returns:
            List[QuoteTypeWeekAggregate]: The totals, in display order.

        Raises:
            KeyError: If a line names a type absent from the mapping.

        Notes:
            - The totals are sums of the amounts already rounded on each line,
              not a re-rounding of an exact sum. That is what makes the weekly
              subtotals on a printed quote add up to its grand total exactly.
            - Unpriced lines are skipped and reported. Including them would make
              the aggregate disagree with the lines beneath it, which on a
              printed quote reads as an arithmetic error rather than as a quote
              that was never fully priced.
        """
        self.logger.debug("Aggregating %d quote line(s).", len(lines))
        buckets: Dict[Tuple[str, int, int], List[QuoteLine]] = {}
        skipped = 0
        for line in lines:
            if not line.is_priced():
                skipped += 1
                continue
            iso_year, iso_week, _ = line.service_date.isocalendar()
            buckets.setdefault(
                (line.intervention_type_id, iso_year, iso_week), []
            ).append(line)
        if skipped:
            self.logger.warning(
                "%d line(s) were left out of the aggregates because they are "
                "not priced.",
                skipped,
            )
        aggregates = [
            self._build(key, bucket, intervention_types)
            for key, bucket in buckets.items()
        ]
        aggregates.sort(key=lambda entry: entry.sort_key())
        self.logger.info(
            "Aggregated %d line(s) into %d type-week total(s).",
            len(lines) - skipped,
            len(aggregates),
        )
        return aggregates

    def price_line(
        self, line: QuoteLine, intervention_type: InterventionType
    ) -> QuoteLine:
        """Return a copy of a line carrying its computed amounts.

        Args:
            line (QuoteLine): The line to price.
            intervention_type (InterventionType): The type it sells.

        Returns:
            QuoteLine: A priced copy. The input is left untouched.

        Notes:
            The effective hourly rate is stored on the line alongside the
            totals, so a quote can show *why* a line cost what it did — a
            customer querying a Sunday visit can be shown the uplifted rate
            rather than being asked to trust the total.
        """
        base_rate = self.base_rate_for(intervention_type)
        multiplier = self.multiplier_for(line.service_date)
        vat_rate = self.vat_rate_for(line)

        effective_rate = base_rate * multiplier
        total_ht = self._to_cents(effective_rate * line.duration_hours())
        vat_amount = self._to_cents(total_ht * vat_rate)

        self.logger.debug(
            "Priced %r on %s: %s x %s x %sh = %s HT, %s VAT.",
            line.name,
            line.service_date,
            base_rate,
            multiplier,
            line.duration_hours(),
            total_ht,
            vat_amount,
        )
        return line.model_copy(
            update={
                "hourly_rate_ht": self._to_cents(effective_rate),
                "total_ht": total_ht,
                "vat_amount": vat_amount,
                "total_ttc": total_ht + vat_amount,
            }
        )

    def price_quote(
        self, quote: Quote, intervention_types: Dict[str, InterventionType]
    ) -> Quote:
        """Return a copy of a quote with every line priced and aggregated.

        Args:
            quote (Quote): The quote to price.
            intervention_types (Dict[str, InterventionType]): The types behind
                its lines, keyed by identifier.

        Returns:
            Quote: A priced copy, carrying its weekly aggregates.

        Raises:
            MTPricingUnknownInterventionType: If a line names a type that is
                absent from the mapping.

        Notes:
            A missing type is fatal rather than skipped. Pricing a line without
            its type would mean guessing both the rate and the VAT category,
            and a quote that is silently short a line is worse than one that
            refuses to price.
        """
        self.logger.info(
            "Pricing quote %s with %d line(s).",
            quote.reference,
            len(quote.lines),  # noqa: E501
        )
        priced_lines: List[QuoteLine] = []
        for line in quote.lines:
            intervention_type = intervention_types.get(line.intervention_type_id)  # noqa: E501
            if intervention_type is None:
                self.logger.error(
                    "Quote %s line %r names the unknown type %s.",
                    quote.reference,
                    line.name,
                    line.intervention_type_id,
                )
                raise MTPricingUnknownInterventionType(
                    f"Quote line {line.name!r} names intervention type "
                    f"{line.intervention_type_id!r}, which does not exist."
                )
            priced_lines.append(self.price_line(line, intervention_type))

        # **Every line keeps its own amounts; only the totals shrink.** The
        # aggregates are what `total_ht`, `total_vat` and `total_ttc` sum, so
        # aggregating over the effective lines alone is what makes a shortened
        # quote cost what it still delivers. Pricing the dropped lines anyway
        # means the quote can still show what each cancelled visit would have
        # cost — which is the question a family asks when the invoice comes in
        # under the quote they signed.
        delivered = quote.model_copy(update={"lines": priced_lines}).effective_lines()
        if len(delivered) != len(priced_lines):
            self.logger.info(
                "Quote %s is interrupted on %s: pricing %d of %d line(s).",
                quote.reference,
                quote.interrupted_on,
                len(delivered),
                len(priced_lines),
            )
        aggregates = self.aggregate(delivered, intervention_types)
        priced = quote.model_copy(
            update={"lines": priced_lines, "aggregates": aggregates}
        )
        self.logger.info(
            "Quote %s totals %s HT, %s VAT, %s TTC across %d week-type group(s).",
            quote.reference,
            priced.total_ht(),
            priced.total_vat(),
            priced.total_ttc(),
            len(aggregates),
        )
        if not priced.lines:
            self.logger.warning(
                "Quote %s has no lines; it totals nothing and cannot be sent.",
                quote.reference,
            )
        return priced
