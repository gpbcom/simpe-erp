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

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        resolved_logger = logger if logger else getLogger(__name__)
        super().__init__(
            session=session, row_class=InterventionRow, logger=resolved_logger
        )
        self.mapper = InterventionMapper(logger=resolved_logger)

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
            One aggregate query rather than loading the visits and taking the
            extremes in Python. Somebody being deleted may have hundreds of
            them, and the two dates are all the caller wants.

            A read, so a database error is logged and reported as "no future
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
            "%s %s is planned from %s to %s; that is the period to replan.",
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
        period_start: date,
        period_end: date,
        interventions: List[Intervention],
    ) -> int:
        """Swap one agency's plan for a period for a freshly computed one.

        Args:
            company_id (str): The agency whose calendar is being rewritten.
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
            - **Scoped to the agency, first and above all.** This is the most
              destructive statement in the application, and until the agency
              was part of it, a run replanning one agency's week deleted every
              *other* agency's visits in the same days and then wrote none of
              them back. Two agencies solving overlapping periods is the normal
              case rather than a rare race — the broker gives each its own
              queue precisely so their runs proceed at the same time — so this
              lost calendars routinely rather than occasionally.
            - The agency is taken as a parameter rather than read off the
              visits. A run that placed nothing still has a period to clear,
              and an empty list would leave the delete with nothing to scope
              itself by.
        """
        self.logger.info(
            "Replacing the plan of agency %s for %s to %s with %d visit(s).",
            company_id,
            period_start,
            period_end,
            len(interventions),
        )
        await self._lock_company(company_id)
        await self.session.execute(
            delete(InterventionRow).where(
                InterventionRow.company_id == company_id,
                InterventionRow.day >= period_start,
                InterventionRow.day <= period_end,
            )
        )
        for intervention in interventions:
            self.session.add(self.mapper.to_row(intervention))
        await self.session.flush()
        if not interventions:
            self.logger.warning(
                "The new plan of agency %s for %s to %s is empty; every "
                "calendar in that period is now blank.",
                company_id,
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
                "Customer %s has no visit between %s and %s; anything billed "
                "for them was never placed by a planning run.",
                customer_id,
                period_start,
                period_end,
            )
        self.logger.info("Loaded %d visit(s) for customer %s.", len(rows), customer_id)
        return [self.mapper.to_model(row) for row in rows]

    async def list_hca_ids_for_period(
        self, period_start: date, period_end: date
    ) -> List[str]:
        """Return which assistants have work in a period.

        Args:
            period_start (date): First day of interest, inclusive.
            period_end (date): Last day of interest, inclusive.

        Returns:
            List[str]: The assistants' identifiers.

        Notes:
            Used to build the manager's whole-workforce view without loading
            every visit first: the diaries are then fetched one assistant at a
            time, through the same scoped read an assistant would use.
        """
        statement = (
            select(InterventionRow.hca_id)
            .where(
                InterventionRow.day >= period_start,
                InterventionRow.day <= period_end,
            )
            .distinct()
        )
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
            **This is what a replan after a deletion is scoped to.** Deleting
            somebody invalidates exactly the days they were due to work, so
            replanning a fixed window instead would either rewrite calendars
            nothing changed on or miss a visit at the edge of it. ``None`` is
            the honest answer that no run is needed at all — queueing one that
            would place the same visits in the same slots is thirty seconds of
            a worker and a calendar that flickers for no reason.

            Days in the past are excluded because they have already happened.
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

    async def count_for_period(self, period_start: date, period_end: date) -> int:
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

    async def update(self, intervention: Intervention) -> Optional[Intervention]:
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
            self.logger.warning("Update requested for an intervention with no id.")
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
                "Nothing to delete: no intervention %s exists.", intervention_id
            )
        return removed
