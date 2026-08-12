from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, FrozenSet, List, Optional, Tuple

# Third-party imports
from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import QuoteStatus
from models.planning.planning_run.unplaced_quote import UnplacedQuote
from models.quoting.quote import Quote
from models.schemas.requests.quoting.quote_filter import QuoteFilter
from storage.mappers.quoting.quote_mapper import QuoteMapper
from storage.orm.quoting.quote_line_row import QuoteLineRow
from storage.orm.quoting.quote_row import QuoteRow
from storage.repositories.base import BaseRepository


class QuoteRepository(BaseRepository[QuoteRow]):
    """Reads and writes quotes, with their lines and weekly totals.

    Attributes:
        LIVE_STATUSES (ClassVar[FrozenSet[QuoteStatus]]): The statuses whose
            hours count as work a team is already carrying.
        mapper (QuoteMapper): Converts between rows and domain models.

    Notes:
        - A quote always travels whole. Every read loads its lines and
          aggregates, and every write replaces them — a header without its lines
          is a quote that prints blank, and there is no use case for one.
        - :attr:`LIVE_STATUSES` is deliberately wider than
          :attr:`~models.quoting.quote.Quote.SCHEDULABLE_STATUSES`. The planner
          schedules only accepted work; the *workload* a team is carrying
          includes what it has offered and is waiting on, because a team with
          twenty quotes out is not a team to send the next one to. Rejected and
          expired quotes are excluded — that is work the agency is not doing.
    """

    LIVE_STATUSES: ClassVar[FrozenSet[QuoteStatus]] = frozenset(
        {
            QuoteStatus.DRAFT,
            QuoteStatus.PENDING_VALIDATION,
            QuoteStatus.SENT,
            QuoteStatus.ACCEPTED,
        }
    )

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        super().__init__(session=session, row_class=QuoteRow)
        self.mapper = QuoteMapper()

    ############################
    # Internal Helpers Methods #
    ############################

    async def _clear_children(self, row: QuoteRow) -> None:
        """Delete a quote's lines and aggregates before they are replaced.

        Args:
            row (QuoteRow): The quote whose children are being replaced.

        Notes:
            - Assigning a new list to a ``delete-orphan`` relationship does not
              guarantee the deletes are emitted before the inserts, and the
              aggregates carry a unique index on
              ``(quote, type, iso_year, iso_week)``. Repricing a quote produces
              the same natural keys, so without flushing the removals first the
              new rows collide with the old ones and the update fails.
            - Cheap regardless: both collections are already loaded, and a
              repriced quote replaces all of them anyway.
        """
        self.logger.debug("Clearing the children of quote %s before update.", row.id)  # noqa: E501
        row.lines.clear()
        row.aggregates.clear()
        await self.session.flush()

    def _build_query(
        self,
        customer_id: Optional[str] = None,
        status: Optional[QuoteStatus] = None,
        authored_by: Optional[str] = None,
        quote_filter: Optional[QuoteFilter] = None,
        team_ids: Optional[List[str]] = None,
    ) -> Select[Tuple[QuoteRow]]:
        """Build the filtered select shared by ``list`` and ``count``.

        Args:
            customer_id (Optional[str]): Restrict to one customer.
            status (Optional[QuoteStatus]): Restrict to one status.
            authored_by (Optional[str]): Restrict to one author's quotes.
            quote_filter (Optional[QuoteFilter]): The richer filter from the
                screen. Its own fields win over the three named arguments.
            team_ids (Optional[List[str]]): The teams whose quotes the caller
                may read. ``None`` means every team; an **empty list means
                none**.

        Returns:
            Select: The filtered statement, without ordering or pagination.

        Notes:
            - ``authored_by`` is what confines an assistant to their own work.
              It is applied here, in the statement, rather than by filtering
              rows after they are read: a page of fifty that is then narrowed to
              three has already loaded forty-seven quotes the caller may not
              see.
            - **The named arguments survive the filter, and the narrower of the
              two always wins.** ``authored_by`` in particular is a permission
              rather than a preference — a filter that could widen it would let
              an assistant list the agency's whole quote book by sending
              ``?authored_by=``.
            - ``team_ids`` is the manager's narrowing, and it distinguishes
              ``None`` from ``[]`` **because getting those the wrong way round
              opens the whole company**. ``None`` is an administrator, who sees
              every team; ``[]`` is a manager who runs no team, or an assistant
              on none, and they must see nothing. Code that treated the empty
              list as "no filter" — the natural falsy reading — would hand the
              second group everything.
        """
        applied = quote_filter or QuoteFilter()
        self.logger.debug(
            "Building the quote query from %s.",
            applied.model_dump(exclude_none=True),  # noqa: E501
        )
        if applied.is_empty() and not any((customer_id, status, authored_by)):
            self.logger.info("No filter was given; the query is every quote.")

        statement = select(QuoteRow)
        if team_ids is not None:
            if not team_ids:
                self.logger.warning(
                    "The caller may read no team; the quote query matches nothing."
                )
            statement = statement.where(QuoteRow.team_id.in_(team_ids))
        if customer_id is not None:
            statement = statement.where(QuoteRow.customer_id == customer_id)
        if authored_by is not None:
            statement = statement.where(QuoteRow.authored_by == authored_by)
        if status is not None:
            statement = statement.where(QuoteRow.status == status.value)

        if applied.customer_id and customer_id is None:
            statement = statement.where(QuoteRow.customer_id == applied.customer_id)  # noqa: E501
        if applied.authored_by and authored_by is None:
            statement = statement.where(QuoteRow.authored_by == applied.authored_by)  # noqa: E501
        elif applied.authored_by and applied.authored_by != authored_by:
            self.logger.warning(
                "A quote filter asked for author %r while the caller is scoped "
                "to %r; the scope wins.",
                applied.authored_by,
                authored_by,
            )
        if applied.status is not None and status is None:
            statement = statement.where(QuoteRow.status == applied.status.value)  # noqa: E501
        for fragment, column in (
            (applied.search, QuoteRow.reference),
            (applied.reference, QuoteRow.reference),
        ):
            if fragment:
                statement = statement.where(
                    column.ilike(f"%{fragment.strip().lower()}%")
                )
        if applied.auto_renew is not None:
            statement = statement.where(QuoteRow.auto_renew.is_(applied.auto_renew))  # noqa: E501
        if applied.is_ongoing is not None:
            today = date.today()
            self.logger.info(
                "Ongoing means accepted and not interrupted before %s.", today
            )
            ongoing = (QuoteRow.status == QuoteStatus.ACCEPTED.value) & or_(
                QuoteRow.interrupted_on.is_(None),
                QuoteRow.interrupted_on >= today,
            )
            statement = statement.where(ongoing if applied.is_ongoing else ~ongoing)  # noqa: E501
        return statement

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, quote: Quote) -> Quote:
        """Insert a new quote.

        Args:
            quote (Quote): The quote to store.

        Returns:
            Quote: The stored quote, carrying its identifiers.

        Raises:
            SQLAlchemyError: If the insert fails — notably when the reference
                is already used, or a line names a type that does not exist.
        """
        self.logger.info(
            "Creating quote %s for customer %s with %d line(s).",
            quote.reference,
            quote.customer_id,
            len(quote.lines),
        )
        row = self.mapper.to_row(quote)
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return self.mapper.to_model(row)

    async def get(self, quote_id: str) -> Optional[Quote]:
        """Return a quote by identifier.

        Args:
            quote_id (str): The identifier to look up.

        Returns:
            Optional[Quote]: The quote, or ``None`` when absent.
        """
        row = await self._get_row(quote_id)
        if row is None:
            self.logger.warning("Quote %s not found.", quote_id)
            return None
        return self.mapper.to_model(row)

    async def get_by_line(self, line_id: str) -> Optional[Quote]:
        """Return the quote one line belongs to.

        Args:
            line_id (str): The line to look the quote up by.

        Returns:
            Optional[Quote]: The whole quote, or ``None`` when no such line
            exists.

        Notes:
            A scheduled visit knows which line it came from and nothing else
            about the paperwork. This is what turns that back into a quote, so
            editing a visit can reprice the thing the customer is billed on
            rather than leaving the two to disagree.
        """
        self.logger.debug("Looking up the quote carrying line %s.", line_id)
        row = await self._fetch_one(
            select(QuoteRow)
            .join(QuoteLineRow, QuoteLineRow.quote_id == QuoteRow.id)
            .where(QuoteLineRow.id == line_id)
        )
        if row is None:
            self.logger.warning("No quote carries a line %s.", line_id)
            return None
        return self.mapper.to_model(row)

    async def get_by_reference(self, reference: str) -> Optional[Quote]:
        """Return a quote by its human-facing number.

        Args:
            reference (str): The reference to look up.

        Returns:
            Optional[Quote]: The quote, or ``None`` when absent.
        """
        normalized = reference.strip().upper()
        self.logger.debug("Looking up quote by reference %s.", normalized)
        row = await self._fetch_one(
            select(QuoteRow).where(QuoteRow.reference == normalized)
        )
        if row is None:
            self.logger.warning("No quote with reference %s.", normalized)
            return None
        return self.mapper.to_model(row)

    async def update(self, quote: Quote) -> Optional[Quote]:
        """Replace a stored quote with a new version of it.

        Args:
            quote (Quote): The quote to store, carrying its identifier.

        Returns:
            Optional[Quote]: The updated quote, or ``None`` when absent.

        Raises:
            SQLAlchemyError: If the update fails.
        """
        if quote.id is None:
            self.logger.warning("Update requested for a quote with no id.")
            return None
        row = await self._get_row(quote.id)
        if row is None:
            self.logger.warning("Update requested for absent quote %s.", quote.id)  # noqa: E501
            return None
        await self._clear_children(row)
        self.mapper.apply_to_row(row, quote)
        await self.session.flush()
        await self.session.refresh(row)
        self.logger.info("Updated quote %s.", quote.reference)
        return self.mapper.to_model(row)

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
            List[Quote]: The matching quotes, newest reference first.
        """
        self.logger.debug(
            "Listing quotes: page=%d customer=%s status=%s author=%s.",
            page,
            customer_id,
            status.value if status else None,
            authored_by,
        )
        statement = self._build_query(
            customer_id, status, authored_by, quote_filter, team_ids
        ).order_by(QuoteRow.reference.desc())
        rows = await self._fetch_all(self._paginate(statement, page, size))
        if not rows:
            self.logger.warning("No quote matched the query.")
        return [self.mapper.to_model(row) for row in rows]

    async def list_renewable(self, today: date) -> List[Quote]:
        """Return the quotes that opted into renewal and have expired.

        Args:
            today (date): The day to measure expiry against.

        Returns:
            List[Quote]: The candidates, oldest expiry first.

        Notes:
            - Expiry is strict: a quote whose ``valid_until`` is today is still
              valid, and renewing it would end an arrangement a day early.
            - Only accepted quotes are considered. A draft that expired was never
              an arrangement, and renewing one would put work on the planner that
              no customer ever agreed to.
        """
        self.logger.debug("Listing quotes renewable as of %s.", today)
        statement = (
            select(QuoteRow)
            .where(QuoteRow.auto_renew.is_(True))
            .where(QuoteRow.valid_until.is_not(None))
            .where(QuoteRow.valid_until < today)
            .where(QuoteRow.status == QuoteStatus.ACCEPTED.value)
            .where(QuoteRow.interrupted_on.is_(None))
            .order_by(QuoteRow.valid_until.asc())
        )
        rows = await self._fetch_all(statement)
        if not rows:
            self.logger.debug("Nothing is due for renewal.")
        return [self.mapper.to_model(row) for row in rows]

    async def has_successor(self, quote_id: str) -> bool:
        """Return whether a quote has already been renewed.

        Args:
            quote_id (str): The parent quote.

        Returns:
            bool: ``True`` when some quote records this one as its parent.

        Notes:
            This is what makes the renewal sweep safe to put on a timer. Two
            workers waking together, or a retry after a partial failure, would
            otherwise each write a successor and the customer would be billed
            twice for the same period.
        """
        statement = select(QuoteRow.id).where(QuoteRow.renewed_from_id == quote_id)  # noqa: E501
        existing = await self._fetch_all(statement.limit(1))  # noqa: E501
        return bool(existing)

    async def count(
        self,
        customer_id: Optional[str] = None,
        status: Optional[QuoteStatus] = None,
        authored_by: Optional[str] = None,
        quote_filter: Optional[QuoteFilter] = None,
        team_ids: Optional[List[str]] = None,
    ) -> int:
        """Return how many quotes match a query.

        Args:
            customer_id (Optional[str]): Restrict to one customer.
            status (Optional[QuoteStatus]): Restrict to one status.
            authored_by (Optional[str]): Restrict to one author's quotes.
            quote_filter (Optional[QuoteFilter]): The screen's filter, so a
                page and its total can never come from different filters.
            team_ids (Optional[List[str]]): The teams the caller may read, so
                the total is narrowed exactly as the page is.

        Returns:
            int: The number of matching quotes.
        """
        return await self._count(
            self._build_query(customer_id, status, authored_by, quote_filter, team_ids)
        )

    async def customer_ids_for_teams(self, team_ids: List[str]) -> List[str]:
        """Return the households a set of teams holds quotes for.

        Args:
            team_ids (List[str]): The teams whose book is being read.

        Returns:
            List[str]: The distinct household identifiers, in identifier order.

        Notes:
            - **Read off the quotes, not off the visits.** A household that has
              been quoted but not yet planned is still the manager's business —
              they are the one chasing the decision — and a scope built from the
              calendar would hide exactly the prospects a manager most needs to
              see.
            - Every status counts, including rejected and expired. A household
              whose quote was declined is somebody the manager spoke to, and
              dropping them from the book would make the record of that
              conversation unreachable.
            - An empty argument returns an empty list without a statement: it
              means a caller who runs no team, and the answer is already known.
        """
        if not team_ids:
            self.logger.warning("No team was given; no household is in scope.")
            return []
        statement = (
            select(QuoteRow.customer_id)
            .where(QuoteRow.team_id.in_(team_ids))
            .distinct()
            .order_by(QuoteRow.customer_id)
        )
        result = await self.session.execute(statement)
        identifiers = [row for row in result.scalars().all() if row]
        self.logger.info(
            "%d household(s) are served by %d team(s).",
            len(identifiers),
            len(team_ids),
        )
        return identifiers

    async def list_schedulable(
        self,
        company_id: str,
        team_id: Optional[str],
        period_start: date,
        period_end: date,
    ) -> List[Quote]:
        """Return accepted quotes with work inside a period.

        Args:
            company_id (str): The agency whose workload is being read.
            team_id (Optional[str]): The team whose share of it is wanted, or
                ``None`` for the whole agency's.
            period_start (date): First day of the window.
            period_end (date): Last day of the window.

        Returns:
            List[Quote]: Every accepted quote in scope with at least one line
            in range.

        Notes:
            - Unpaginated by design: a planning run needs the whole workload at
              once, and paging through it would build a plan from a moving
              target.
            - **Ordered, and that is a determinism requirement rather than a
              presentational one.** See the comment on the statement itself.
            - The filter is on the **line** dates, not the quote's issue date. A
              quote issued in January can carry work in March, and asking by
              issue date would either miss it or drag in months of irrelevant
              history.
            - A returned quote may still hold lines outside the window; the
              requirement builder filters those. Loading the quote whole keeps
              its totals consistent with what was accepted.
            - **Scoped to the agency and to the team.** This is the input half
              of what
              :meth:`~storage.repositories.planning.intervention.InterventionRepository.replace_for_period`
              is the output half of, and the two must be scoped alike. Unscoped
              by agency, a run would build one agency's week out of every
              agency's accepted work; unscoped by team, it would build one
              team's week out of a sister team's work, hand those visits to its
              own assistants, and then — because the output half *is* scoped —
              write them into the first team's calendar while the second team's
              own run wrote them again into hers. The same household would be
              visited twice by two teams, and each run would look correct on its
              own.
            - Both are parameters with no default, for the same reason the
              agency is one on
              :meth:`~service.messaging.publisher.EventPublisher.publish` — a
              forgotten argument must be a ``TypeError`` at the call site, not a
              silently wider query.
        """
        self.logger.info(
            "Loading the schedulable quotes of team %s at agency %s between %s and %s.",
            team_id,
            company_id,
            period_start,
            period_end,
        )
        statement = (
            select(QuoteRow)
            .join(QuoteLineRow, QuoteLineRow.quote_id == QuoteRow.id)
            .where(
                QuoteRow.company_id == company_id,
                QuoteRow.status == QuoteStatus.ACCEPTED.value,
                QuoteLineRow.service_date >= period_start,
                QuoteLineRow.service_date <= period_end,
            )
            .distinct()
            .order_by(QuoteRow.id)
        )
        if team_id is not None:
            statement = statement.where(QuoteRow.team_id == team_id)
        rows = await self._fetch_all(statement)
        if not rows:
            self.logger.warning(
                "No accepted quote of %s covers %s to %s; a planning run "
                "would have nothing to schedule.",
                f"team {team_id}" if team_id else "the agency",
                period_start,
                period_end,
            )
        self.logger.info("Loaded %d schedulable quote(s).", len(rows))
        return [self.mapper.to_model(row) for row in rows]

    async def assigned_minutes_by_team(
        self, company_id: str, team_ids: List[str]
    ) -> Dict[str, int]:
        """Return how much work each team already carries, in minutes.

        Args:
            company_id (str): The company whose quotes are being measured.
            team_ids (List[str]): The teams to measure.

        Returns:
            Dict[str, int]: Minutes per team, **one entry per team asked for**.

        Notes:
            - The busyness half of the quote-to-team rule. Measured over quotes
              that are still live — draft, awaiting validation, sent and
              accepted — rather than over planned visits, because a company that
              has never run the planner would otherwise measure every team at
              zero and send every quote to the first one.
            - **Every team asked for gets an entry, seeded to zero.** A
              ``GROUP BY`` returns no row for a team with no quotes at all, and
              reading a missing key as "unknown, therefore last" would send
              every new quote to the busiest team — the exact opposite of the
              rule. The seeding is what makes a brand-new team the one that
              wins.
            - Rejected and expired quotes are excluded. They are work the agency
              is not doing, and counting them would keep a team looking busy
              because of offers a customer turned down.
        """
        if not team_ids:
            self.logger.debug("No team to measure the workload of.")
            return {}
        minutes: Dict[str, int] = {team_id: 0 for team_id in team_ids}
        statement = (
            select(
                QuoteRow.team_id,
                func.coalesce(func.sum(QuoteLineRow.duration_minutes), 0),
            )
            .join(QuoteLineRow, QuoteLineRow.quote_id == QuoteRow.id)
            .where(
                QuoteRow.company_id == company_id,
                QuoteRow.team_id.in_(team_ids),
                QuoteRow.status.in_([status.value for status in self.LIVE_STATUSES]),  # noqa: E501
            )
            .group_by(QuoteRow.team_id)
        )
        result = await self.session.execute(statement)
        for team_id, total in result.all():
            minutes[str(team_id)] = int(total)
        self.logger.debug(
            "Measured the workload of %d team(s) of company %s.",
            len(minutes),
            company_id,
        )
        return minutes

    async def count_for_team(self, team_id: str) -> int:
        """Return how many quotes a team holds, in any status.

        Args:
            team_id (str): The team to count for.

        Returns:
            int: The number of quotes.

        Notes:
            What the team-deletion refusal is built on. ``quotes.team_id``
            carries no foreign key, so nothing stops a quote outliving its team
            — and a quote naming a team that no longer exists is one no planning
            run will ever read again.
        """
        statement = select(QuoteRow).where(QuoteRow.team_id == team_id)
        total = await self._count(statement)
        self.logger.debug("Team %s holds %d quote(s).", team_id, total)
        return total

    async def delete(self, quote_id: str) -> bool:
        """Delete a quote and its lines.

        Args:
            quote_id (str): The quote to delete.

        Returns:
            bool: ``True`` when a row was deleted.

        Raises:
            SQLAlchemyError: If the delete fails.
        """
        try:
            return await self._delete_row(quote_id)
        except SQLAlchemyError as exc:
            self.logger.error("Error deleting quote %s: %s.", quote_id, exc)
            raise

    async def set_status(self, quote_id: str, status: QuoteStatus) -> Optional[Quote]:  # noqa: E501
        """Move a quote to another point in its lifecycle.

        Args:
            quote_id (str): The quote to move.
            status (QuoteStatus): The new status.

        Returns:
            Optional[Quote]: The updated quote, or ``None`` when absent.

        Notes:
            A narrow method: accepting a quote must not be able to change its
            lines at the same time. What the customer accepted is what was sent
            to them.
        """
        row = await self._get_row(quote_id)
        if row is None:
            self.logger.warning(
                "Status change requested for absent quote %s.", quote_id
            )
            return None
        self.logger.info(
            "Quote %s moves from %s to %s.",
            row.reference,
            row.status,
            status.value,  # noqa: E501
        )
        row.status = status.value
        await self.session.flush()
        await self.session.refresh(row)
        return self.mapper.to_model(row)

    async def set_planning_feedback(
        self, quote_id: str, feedback: Optional[UnplacedQuote]
    ) -> Optional[Quote]:
        """Record why the last planning could not fit this quote's work.

        Args:
            quote_id (str): The quote to annotate.
            feedback (Optional[UnplacedQuote]): The report, or ``None`` to
                clear it once the work fits again.

        Returns:
            Optional[Quote]: The updated quote, or ``None`` when absent.

        Notes:
            Narrow, like :meth:`set_status` beside it, and for the same
            reason: recording why a week did not fit must not be able to
            change what was quoted. The two are called together — a quote that
            goes back to the validation queue without saying why looks like
            the system lost it — but they stay separable so that clearing the
            note does not touch the lifecycle.
        """
        row = await self._get_row(quote_id)
        if row is None:
            self.logger.warning(
                "Planning feedback requested for absent quote %s.", quote_id
            )
            return None
        row.planning_feedback = (
            feedback.model_dump(mode="json") if feedback is not None else None
        )
        if feedback is not None:
            self.logger.info(
                "Quote %s records %d unplaced visit(s) and %d offered slot(s).",
                row.reference,
                len(feedback.visits),
                len(feedback.alternatives),
            )
        else:
            self.logger.debug("Quote %s planning feedback cleared.", row.reference)  # noqa: E501
        await self.session.flush()
        await self.session.refresh(row)
        return self.mapper.to_model(row)

    async def record_submission(
        self, quote_id: str, submitted_at: datetime
    ) -> Optional[Quote]:
        """Put a quote into the validation queue.

        Args:
            quote_id (str): The quote being submitted.
            submitted_at (datetime): When it was submitted.

        Returns:
            Optional[Quote]: The updated quote, or ``None`` when absent.

        Notes:
            ``authored_by`` is not written here. It is set when the quote is
            created and never moves: the person who wrote it is not the person
            who happens to press submit, and overwriting it here would erase the
            authorship the assistant's own list is scoped by.
        """
        row = await self._get_row(quote_id)
        if row is None:
            self.logger.warning("Submission requested for absent quote %s.", quote_id)  # noqa: E501
            return None
        self.logger.info(
            "Quote %s moves from %s to %s.",
            row.reference,
            row.status,
            QuoteStatus.PENDING_VALIDATION.value,
        )
        row.status = QuoteStatus.PENDING_VALIDATION.value
        row.submitted_at = submitted_at
        await self.session.flush()
        await self.session.refresh(row)
        return self.mapper.to_model(row)

    async def record_validation(
        self,
        quote_id: str,
        status: QuoteStatus,
        validated_by: str,
        validated_at: datetime,
        issued_on: Optional[date] = None,
        valid_until: Optional[date] = None,
    ) -> Optional[Quote]:
        """Record a manager's ruling on a submitted quote.

        Args:
            quote_id (str): The quote being ruled on.
            status (QuoteStatus): Where the ruling puts it.
            validated_by (str): The account that ruled.
            validated_at (datetime): When they ruled.
            issued_on (Optional[date]): The day the offer was issued, set when
                the ruling issues it.
            valid_until (Optional[date]): The day the offer lapses.

        Returns:
            Optional[Quote]: The updated quote, or ``None`` when absent.

        Notes:
            Used for both outcomes. ``validated_by`` records who *ruled*, not
            who approved — a refusal is as much a decision somebody must own as
            an approval, and "the quote came back to me and nobody will say who
            sent it back" is the complaint this column exists to prevent.
        """
        row = await self._get_row(quote_id)
        if row is None:
            self.logger.warning("Validation requested for absent quote %s.", quote_id)  # noqa: E501
            return None
        self.logger.info(
            "Quote %s moves from %s to %s, ruled by %s.",
            row.reference,
            row.status,
            status.value,
            validated_by,
        )
        row.status = status.value
        row.validated_by = validated_by
        row.validated_at = validated_at
        if issued_on is not None:
            row.issued_on = issued_on
        if valid_until is not None:
            row.valid_until = valid_until
        await self.session.flush()
        await self.session.refresh(row)
        return self.mapper.to_model(row)
