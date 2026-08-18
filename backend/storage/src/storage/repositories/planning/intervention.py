from __future__ import annotations

# Standard library imports
from datetime import date
from hashlib import blake2b
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third-party imports
from sqlalchemy import ColumnElement, delete, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.planning.intervention import Intervention
from storage.mappers.planning.intervention_mapper import InterventionMapper
from storage.orm.planning.intervention_row import InterventionRow
from storage.repositories.base import BaseRepository


class InterventionRepository(BaseRepository[InterventionRow]):
    """Reads and writes scheduled visits.

    Attributes:
        mapper (InterventionMapper): Converts between rows and domain models.

    Notes:
        Every read is scoped by assistant or by period. There is deliberately
        no "all interventions" method: the one query nobody should be able to
        make casually is the one that returns every assistant's diary at once.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        super().__init__(session=session, row_class=InterventionRow)
        self.mapper = InterventionMapper()

    ############################
    # Internal Helpers Methods #
    ############################

    async def _lock_company(self, company_id: str) -> None:
        """Hold an agency's plan against a concurrent replacement.

        Args:
            company_id (str): The agency to lock.

        Notes:
            - **Transaction-scoped, and taken immediately before the delete.**
              The lock is released when the transaction ends, so nothing has to
              remember to give it back — including a worker killed mid-write.
            - Taken around the *write*, not around the solve. Two runs for one
              agency each produce a complete, internally consistent plan for the
              period, so the later one winning is a correct outcome; what is not
              correct is one run's delete landing between the other's delete and
              its inserts, which is what this prevents. Holding it across the
              thirty-second solve instead would pin a pooled connection for the
              whole budget and buy nothing.
            - Cross-*agency* interference is not what this defends against —
              scoping the statements by ``company_id`` is. This is the
              same-agency half of the same problem.
            - PostgreSQL only, and quietly skipped elsewhere. The advisory lock
              functions are a PostgreSQL feature, and the test schema runs on
              SQLite, which serialises writers anyway and so has nothing to be
              protected from.
        """
        dialect = self.session.get_bind().dialect.name
        if dialect != "postgresql":
            self.logger.debug(
                "Not locking agency %s: %s has no advisory locks.",
                company_id,
                dialect,
            )
            return
        digest = blake2b(company_id.encode("utf-8"), digest_size=8).digest()
        key = int.from_bytes(digest, byteorder="big", signed=True)
        self.logger.debug("Locking the plan of agency %s (key %d).", company_id, key)
        try:
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": key}
            )
        except SQLAlchemyError as exc:
            self.logger.error(
                "Could not lock the plan of agency %s: %s. The replacement "
                "proceeds unserialised.",
                company_id,
                exc,
            )

    async def _span(
        self,
        condition: ColumnElement[bool],
        from_day: date,
        subject: str,
        subject_id: str,
    ) -> Optional[Tuple[date, date]]:
        """Return the first and last future day matching a condition.

        Args:
            condition (ColumnElement[bool]): The row filter to apply, naming
                whose visits are wanted.
            from_day (date): The first day that still counts as future,
                inclusive.
            subject (str): What the filter selects, for the log line.
            subject_id (str): The identifier being measured, for the log line.

        Returns:
            Optional[Tuple[date, date]]: The span, or ``None`` when nothing
            matched.

        Notes:
            - One aggregate query rather than loading the visits and taking the
              extremes in Python. Somebody being deleted may have hundreds of
              them, and the two dates are all the caller wants.
            - A read, so a database error is logged and reported as "no future
              work" rather than raised. The delete that follows must not be
              blocked by a failure to work out how much of the calendar it
              disturbs — the person still has to go, and a run can be asked for
              by hand.
        """
        statement = select(
            func.min(InterventionRow.day), func.max(InterventionRow.day)
        ).where(condition, InterventionRow.day >= from_day)
        try:
            result = await self.session.execute(statement)
            first, last = result.one()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Error measuring the remaining visits of %s %s: %s.",
                subject,
                subject_id,
                exc,
            )
            return None
        if first is None or last is None:
            self.logger.debug(
                "No visit is planned for %s %s from %s onward.",
                subject,
                subject_id,
                from_day,
            )
            return None
        self.logger.info(
            "%s %s is planned from %s to %s. That is the period to replan.",
            subject.capitalize(),
            subject_id,
            first,
            last,
        )
        return first, last

    ############################
    # Publicly Exposed Methods #
    ############################

    async def replace_for_period(
        self,
        company_id: str,
        team_id: str,
        period_start: date,
        period_end: date,
        interventions: List[Intervention],
    ) -> int:
        """Swap one team's plan for a period for a freshly computed one.

        Args:
            company_id (str): The agency whose calendar is being rewritten.
            team_id (str): The team whose part of it is being rewritten.
            period_start (date): First day replaced, inclusive.
            period_end (date): Last day replaced, inclusive.
            interventions (List[Intervention]): The new plan.

        Returns:
            int: How many visits were written.

        Notes:
            - The delete and the insert happen in one transaction, so a period
              is never briefly empty — an assistant refreshing mid-replan sees
              the old plan or the new one, never a blank week.
            - Scoped to the period rather than the run: a re-plan of one week
              must not disturb the week after it, which a different run
              produced.
            - **Scoped to the agency and to the team, first and above all.**
              This is the most destructive statement in the application. Until
              the agency was part of it, a run replanning one agency's week
              deleted every *other* agency's visits in the same days and then
              wrote none of them back. The team half is the identical bug one
              level down, and now the likelier of the two — a manager
              re-planning their own team is an everyday act, and every other
              team of the same agency would lose the week.
            - Both are taken as **parameters** rather than read off the visits.
              A run that placed nothing still has a period to clear, and an
              empty list would leave the delete with nothing to scope itself
              by — which is precisely the case that would wipe everything.
            - The lock stays keyed on the **agency**, not the team. Two teams'
              runs touch disjoint rows, so serialising them costs a moment and
              buys the existing guarantee unchanged. Keying it per team would
              need the delete's correctness to rest on the scoping alone, and
              the scoping is what this note exists to say has been wrong before.
        """
        self.logger.info(
            "Replacing the plan of team %s at agency %s for %s to %s with %d visit(s).",
            team_id,
            company_id,
            period_start,
            period_end,
            len(interventions),
        )
        await self._lock_company(company_id)
        await self.session.execute(
            delete(InterventionRow).where(
                InterventionRow.company_id == company_id,
                InterventionRow.team_id == team_id,
                InterventionRow.day >= period_start,
                InterventionRow.day <= period_end,
            )
        )
        for intervention in interventions:
            self.session.add(self.mapper.to_row(intervention))
        await self.session.flush()
        if not interventions:
            self.logger.warning(
                "The new plan of team %s for %s to %s is empty. That team's "
                "calendars in that period are now blank.",
                team_id,
                period_start,
                period_end,
            )
        return len(interventions)

    async def list_for_hca(
        self, hca_id: str, period_start: date, period_end: date
    ) -> List[Intervention]:
        """Return one assistant's visits over a period.

        Args:
            hca_id (str): The assistant whose diary is being read.
            period_start (date): First day of interest, inclusive.
            period_end (date): Last day of interest, inclusive.

        Returns:
            List[Intervention]: Their visits, in day and time order.

        Notes:
            The assistant is part of the query, not a filter applied after. An
            assistant may read only their own planning, and a method that
            returned everybody's and left the caller to narrow it would make
            that a discipline rather than a property.
        """
        self.logger.debug(
            "Loading the diary of assistant %s from %s to %s.",
            hca_id,
            period_start,
            period_end,
        )
        statement = (
            select(InterventionRow)
            .where(
                InterventionRow.hca_id == hca_id,
                InterventionRow.day >= period_start,
                InterventionRow.day <= period_end,
            )
            .order_by(InterventionRow.day, InterventionRow.start_time)
        )
        rows = await self._fetch_all(statement)
        if not rows:
            self.logger.warning(
                "Assistant %s has no visit between %s and %s.",
                hca_id,
                period_start,
                period_end,
            )
        return [self.mapper.to_model(row) for row in rows]

    async def list_for_customer(
        self, customer_id: str, period_start: date, period_end: date
    ) -> List[Intervention]:
        """Return one customer's visits over a period.

        Args:
            customer_id (str): The customer whose visits are being read.
            period_start (date): First day of interest, inclusive.
            period_end (date): Last day of interest, inclusive.

        Returns:
            List[Intervention]: Their visits, in day and time order.

        Notes:
            - Scoped by customer **and** by period, which is what keeps it
              inside the rule the class docstring sets: there is deliberately no
              "every intervention" method, and this is the same shape as
              :meth:`list_for_hca` with the other party named.
            - Written for billing, which needs the hours actually worked and the
              assistant who worked them so an invoice can say more than "one
              service, 9 March". A customer with quote lines but no visits here
              is a period that was never planned — worth seeing in the log
              beside the invoice it produced, which is why the empty case is a
              warning rather than silence.
            - Served by ``ix_interventions_customer``, which already existed for
              a query nothing had yet written.
        """
        self.logger.debug(
            "Loading the visits of customer %s from %s to %s.",
            customer_id,
            period_start,
            period_end,
        )
        statement = (
            select(InterventionRow)
            .where(
                InterventionRow.customer_id == customer_id,
                InterventionRow.day >= period_start,
                InterventionRow.day <= period_end,
            )
            .order_by(InterventionRow.day, InterventionRow.start_time)
        )
        rows = await self._fetch_all(statement)
        if not rows:
            self.logger.warning(
                "Customer %s has no visit between %s and %s. Anything billed "
                "for them was never placed by a planning run.",
                customer_id,
                period_start,
                period_end,
            )
        self.logger.info("Loaded %d visit(s) for customer %s.", len(rows), customer_id)
        return [self.mapper.to_model(row) for row in rows]

    async def list_hca_ids_for_period(
        self,
        period_start: date,
        period_end: date,
        team_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Return which assistants have work in a period.

        Args:
            period_start (date): First day of interest, inclusive.
            period_end (date): Last day of interest, inclusive.
            team_ids (Optional[List[str]]): The teams the caller may read.
                ``None`` means every team. An **empty list means none**.

        Returns:
            List[str]: The assistants' identifiers.

        Notes:
            - Used to build the workforce view without loading every visit
              first: the diaries are then fetched one assistant at a time,
              through the same scoped read an assistant would use.
            - ``None`` and ``[]`` are not interchangeable. ``None`` is an
              administrator and ``[]`` is somebody who runs no team; reading the
              empty list as "no filter" — the natural falsy reading — would show
              the second group the whole agency's calendar.
        """
        statement = (
            select(InterventionRow.hca_id)
            .where(
                InterventionRow.day >= period_start,
                InterventionRow.day <= period_end,
            )
            .distinct()
        )
        if team_ids is not None:
            statement = statement.where(InterventionRow.team_id.in_(team_ids))
        try:
            result = await self.session.execute(statement)
            identifiers = [row[0] for row in result.all()]
        except Exception as exc:  # noqa: BLE001 - reported as an empty period
            self.logger.error(
                "Error listing the assistants planned between %s and %s: %s.",
                period_start,
                period_end,
                exc,
            )
            return []
        self.logger.debug(
            "%d assistant(s) have work between %s and %s.",
            len(identifiers),
            period_start,
            period_end,
        )
        return identifiers

    async def list_for_customers(
        self, customer_ids: List[str], period_start: date, period_end: date
    ) -> List[Intervention]:
        """Return several households' visits in one read.

        Args:
            customer_ids (List[str]): The households wanted.
            period_start (date): First day of the period, inclusive.
            period_end (date): Last day of the period, inclusive.

        Returns:
            List[Intervention]: Their visits, grouped by household and in time
            order within each.

        Notes:
            - **Exactly what :meth:`list_for_customer` returns, for several
              households at once.** Same predicate on the day, same absence of a
              status filter, same ``(day, start_time)`` order within a
              household. That equivalence is a contract, not a coincidence: the
              single-household read is what the customer portal serves a family
              from, so a filter added here and not there would show the agency
              something the household cannot see. A test asserts the two agree.
            - This does **not** breach the "no unscoped read" rule this class is
              built on. The scope is still an explicitly named set of parties —
              the same rule with a wider ``IN`` — and the caller has already
              decided which households it is entitled to.
            - It exists because the alternative is one query per household. A
              manager's screen covering four hundred households would otherwise
              hold a connection for four hundred round trips, on a page opened
              every morning.
            - An empty input answers without a query: ``IN ()`` is a syntax
              error on some engines, and an assistant with no portfolio is an
              ordinary state rather than a failure.
        """
        if not customer_ids:
            self.logger.debug("No household was named; reading no visit.")
            return []
        statement = (
            select(InterventionRow)
            .where(
                InterventionRow.customer_id.in_(customer_ids),
                InterventionRow.day >= period_start,
                InterventionRow.day <= period_end,
            )
            .order_by(
                InterventionRow.customer_id,
                InterventionRow.day,
                InterventionRow.start_time,
            )
        )
        try:
            result = await self.session.execute(statement)
            rows = list(result.scalars().all())
        except SQLAlchemyError as exc:
            self.logger.error(
                "Error loading the visits of %d household(s) between %s and %s: %s.",
                len(customer_ids),
                period_start,
                period_end,
                exc,
            )
            raise
        if not rows:
            self.logger.warning(
                "None of the %d named household(s) has a visit between %s and %s.",
                len(customer_ids),
                period_start,
                period_end,
            )
        self.logger.info(
            "Loaded %d visit(s) for %d household(s).", len(rows), len(customer_ids)
        )
        return [self.mapper.to_model(row) for row in rows]

    async def list_customer_ids_for_period(
        self,
        period_start: date,
        period_end: date,
        team_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Return which households have care planned in a period.

        Args:
            period_start (date): First day of interest, inclusive.
            period_end (date): Last day of interest, inclusive.
            team_ids (Optional[List[str]]): The teams the caller may read.
                ``None`` means every team. An empty list means none.

        Returns:
            List[str]: The households' identifiers.

        Notes:
            - The mirror of :meth:`list_hca_ids_for_period`, on the other axis,
              and used the same way: the manager's whole-agency view is built
              from it without loading every visit first, then one household at a
              time through :meth:`list_for_customer` — the same scoped read the
              household's own portal uses.
            - Read off the **visits**, not off the customer book. A household
              with nothing planned in the period is not somebody the screen
              passed over. It is somebody there is nothing to show for, and
              listing them would fill a rail with empty weeks.
            - A failure answers an empty period rather than raising, exactly as
              the assistant-side method does: a screen that cannot say who has
              work is a screen that shows nothing, not one that breaks.
            - The team narrowing is what makes a manager's household rail
              *theirs*. It says the same thing the quote-side narrowing does,
              one table over: a household is the manager's business because one
              of their teams delivers to it.
        """
        statement = (
            select(InterventionRow.customer_id)
            .where(
                InterventionRow.day >= period_start,
                InterventionRow.day <= period_end,
            )
            .distinct()
        )
        if team_ids is not None:
            statement = statement.where(InterventionRow.team_id.in_(team_ids))
        try:
            result = await self.session.execute(statement)
            identifiers = [row[0] for row in result.all()]
        except Exception as exc:  # noqa: BLE001 - reported as an empty period
            self.logger.error(
                "Error listing the households planned between %s and %s: %s.",
                period_start,
                period_end,
                exc,
            )
            return []
        if not identifiers:
            self.logger.warning(
                "No household has care planned between %s and %s.",
                period_start,
                period_end,
            )
        self.logger.info(
            "%d household(s) have care between %s and %s.",
            len(identifiers),
            period_start,
            period_end,
        )
        return identifiers

    async def future_period_for_hca(
        self, hca_id: str, from_day: date
    ) -> Optional[Tuple[date, date]]:
        """Return the span of an assistant's remaining visits.

        Args:
            hca_id (str): The assistant whose work is being measured.
            from_day (date): The first day that still counts as future,
                inclusive.

        Returns:
            Optional[Tuple[date, date]]: The first and last day they are
            planned on from ``from_day`` onward, or ``None`` when they have no
            work left.

        Notes:
            - **This is what a replan after a deletion is scoped to.** Deleting
              somebody invalidates exactly the days they were due to work, so
              replanning a fixed window instead would either rewrite calendars
              nothing changed on or miss a visit at the edge of it. ``None`` is
              the honest answer that no run is needed at all — queueing one that
              would place the same visits in the same slots is thirty seconds of
              a worker and a calendar that flickers for no reason.
            - Days in the past are excluded because they have already happened.
              Rewriting them would move visits somebody has already made.
        """
        return await self._span(
            InterventionRow.hca_id == hca_id, from_day, "assistant", hca_id
        )

    async def future_period_for_customer(
        self, customer_id: str, from_day: date
    ) -> Optional[Tuple[date, date]]:
        """Return the span of a customer's remaining visits.

        Args:
            customer_id (str): The customer whose work is being measured.
            from_day (date): The first day that still counts as future,
                inclusive.

        Returns:
            Optional[Tuple[date, date]]: The first and last day they are
            visited on from ``from_day`` onward, or ``None`` when nothing is
            planned for them.

        Notes:
            The customer's own visits vanish with them, and the assistants who
            were going to make them gain a gap somebody else's work can move
            into — which is why this replans rather than simply deleting.
        """
        return await self._span(
            InterventionRow.customer_id == customer_id,
            from_day,
            "customer",
            customer_id,
        )

    async def future_teams_for_person(
        self, column_value: str, is_customer: bool, from_day: date
    ) -> List[str]:
        """Return the teams still holding future visits for one person.

        Args:
            column_value (str): The customer or assistant identifier.
            is_customer (bool): Whether the identifier names a household rather
                than an assistant.
            from_day (date): The first day that still counts as future,
                inclusive.

        Returns:
            List[str]: The distinct teams, in identifier order.

        Notes:
            - **The companion to** :meth:`future_period_for_hca` **and**
              :meth:`future_period_for_customer`. Those two say *when* a replan
              is needed. This says *whose*. Since a run rewrites one team's week,
              a deletion that touched two teams needs two runs — and asking the
              database which teams is the only way to know, because a household
              can hold quotes attributed at different times.
            - Read **before** the deletion, like the period is: once the rows are
              gone there is nothing left to ask.
            - Ordered by identifier so two identical deletions queue their runs
              in the same sequence. Nothing depends on it today. A test
              comparing two runs would.
        """
        subject = InterventionRow.customer_id if is_customer else InterventionRow.hca_id
        statement = (
            select(InterventionRow.team_id)
            .where(subject == column_value, InterventionRow.day >= from_day)
            .distinct()
            .order_by(InterventionRow.team_id)
        )
        result = await self.session.execute(statement)
        team_ids = [team_id for team_id in result.scalars().all() if team_id]
        if not team_ids:
            self.logger.debug(
                "No future visit names %s. No team needs replanning.",
                column_value,
            )
        else:
            self.logger.info(
                "%d team(s) hold future visits for %s.", len(team_ids), column_value
            )
        return team_ids

    async def count_for_period(self, period_start: date, period_end: date) -> int:  # noqa: E501
        """Return how many visits are planned in a period.

        Args:
            period_start (date): First day of interest, inclusive.
            period_end (date): Last day of interest, inclusive.

        Returns:
            int: The number of visits.
        """
        return await self._count(
            select(InterventionRow).where(
                InterventionRow.day >= period_start,
                InterventionRow.day <= period_end,
            )
        )

    async def get(self, intervention_id: str) -> Optional[Intervention]:
        """Return one visit by identifier.

        Args:
            intervention_id (str): The visit wanted.

        Returns:
            Optional[Intervention]: The visit, or ``None`` when absent.

        Notes:
            By identifier and nothing else, which is why this is not the "all
            interventions" query the class documentation refuses: a caller who
            already holds a visit's identifier was given it by a diary they
            were allowed to read.
        """
        self.logger.debug("Loading intervention %s.", intervention_id)
        row = await self._get_row(intervention_id)
        if row is None:
            self.logger.warning("No intervention %s exists.", intervention_id)
            return None
        return self.mapper.to_model(row)

    async def update(self, intervention: Intervention) -> Optional[Intervention]:  # noqa: E501
        """Replace a stored visit with a new version of it.

        Args:
            intervention (Intervention): The visit to store, carrying its
                identifier.

        Returns:
            Optional[Intervention]: The updated visit, or ``None`` when absent.

        Raises:
            SQLAlchemyError: If the update fails.
        """
        if intervention.id is None:
            self.logger.warning("Update requested for an intervention with no id.")  # noqa: E501
            return None
        row = await self._get_row(intervention.id)
        if row is None:
            self.logger.warning(
                "Update requested for absent intervention %s.", intervention.id
            )
            return None
        self.mapper.apply_to_row(row, intervention)
        await self.session.flush()
        await self.session.refresh(row)
        self.logger.info("Updated intervention %s.", intervention.id)
        return self.mapper.to_model(row)

    async def delete(self, intervention_id: str) -> bool:
        """Remove one visit.

        Args:
            intervention_id (str): The visit to remove.

        Returns:
            bool: ``True`` when a row was removed, ``False`` when none existed.

        Notes:
            Removing the visit alone would not keep it removed. The next
            planning run rebuilds the period from the quote lines, so a visit
            whose line still stands comes straight back — which is why the
            caller above this one deletes the line in the same breath.
        """
        self.logger.info("Deleting intervention %s.", intervention_id)
        removed = await self._delete_row(intervention_id)
        if not removed:
            self.logger.warning(
                "Nothing to delete: no intervention %s exists.",
                intervention_id,  # noqa: E501
            )
        return removed
