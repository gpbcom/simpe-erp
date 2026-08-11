from __future__ import annotations

# Standard library imports
from datetime import UTC, date, datetime, time
from typing import Any, Dict, List

# Third-party imports
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import InterventionStatus, PlanningRunStatus
from models.geo.postal_address import PostalAddress
from models.people.hca import Hca
from models.planning.intervention import Intervention
from models.planning.planning_run import PlanningRun
from storage.repositories.people.hca import HcaRepository
from storage.repositories.planning.intervention import InterventionRepository
from storage.repositories.planning.planning_run import PlanningRunRepository

MONDAY = date(2026, 8, 3)
TUESDAY = date(2026, 8, 4)
NEXT_MONDAY = date(2026, 8, 10)


async def _hca(session: AsyncSession, kwargs: Dict[str, Any], email: str) -> str:
    """Store an assistant and return its identifier.

    Args:
        session (AsyncSession): The open session.
        kwargs (Dict[str, Any]): Assistant constructor arguments.
        email (str): The address to give this one, which must be unique.

    Returns:
        str: The stored assistant's identifier.
    """
    stored = await HcaRepository(session).create(
        Hca(company_id="company-1", **{**kwargs, "email": email})
    )
    return stored.id


def _visit(
    hca_id: str,
    run_id: str,
    day: date = MONDAY,
    start: time = time(9, 0),
    name: str = "Toilette matin",
) -> Intervention:
    """Build a visit ready to store.

    Args:
        hca_id (str): The assistant performing it.
        run_id (str): The run that produced it.
        day (date): The day it happens.
        start (time): When it begins.
        name (str): What the service is.

    Returns:
        Intervention: The unsaved visit.
    """
    return Intervention(
        company_id="company-1",
        planning_run_id=run_id,
        name=name,
        intervention_type_id="type-1",
        quote_line_id="line-1",
        hca_id=hca_id,
        hca_full_name="Luc Martin",
        customer_id="customer-1",
        day=day,
        start_time=start,
        end_time=time(start.hour + 1, start.minute),
        address=PostalAddress(
            street="12 rue de Rivoli",
            postal_code="75004",
            city="Paris",
            latitude=48.8566,
            longitude=2.3522,
        ),
        status=InterventionStatus.PLANNED,
    )


async def _run(session: AsyncSession, status: PlanningRunStatus) -> PlanningRun:
    """Store a planning run and return it.

    Args:
        session (AsyncSession): The open session.
        status (PlanningRunStatus): The status to store it with.

    Returns:
        PlanningRun: The stored run, carrying its identifier.
    """
    return await PlanningRunRepository(session).create(
        PlanningRun(
            company_id="company-1",
            status=status,
            requested_by="admin-1",
            period_start=MONDAY,
            period_end=date(2026, 8, 9),
        )
    )


class TestPlanningRunRepository:
    """Tests for the run record's persistence."""

    # ------------------------------------------------------------------ #
    #  Round trip
    # ------------------------------------------------------------------ #

    async def test_a_stored_run_comes_back_as_it_went_in(
        self, session: AsyncSession
    ) -> None:
        """Every field survives the round trip."""
        stored = await _run(session, PlanningRunStatus.PENDING)
        loaded = await PlanningRunRepository(session).get(stored.id)

        assert loaded is not None
        assert loaded.status is PlanningRunStatus.PENDING
        assert loaded.requested_by == "admin-1"
        assert loaded.period_start == MONDAY
        assert loaded.period_end == date(2026, 8, 9)

    async def test_unassigned_identifiers_survive_the_round_trip(
        self, session: AsyncSession
    ) -> None:
        """The list of what would not fit is stored, not dropped.

        Notes:
            This list is the whole point of a succeeded-with-gaps run. Losing
            it would leave a planner told the run worked and no way to see
            which work went unplaced.
        """
        stored = await _run(session, PlanningRunStatus.SUCCEEDED)
        repository = PlanningRunRepository(session)
        await repository.update(
            stored.model_copy(
                update={"unassigned_requirement_ids": ["line-7", "line-9"]}
            )
        )

        loaded = await repository.get(stored.id)
        assert loaded is not None
        assert loaded.unassigned_requirement_ids == ["line-7", "line-9"]

    async def test_an_empty_unassigned_list_stays_empty(
        self, session: AsyncSession
    ) -> None:
        """A clean run comes back with an empty list, not ``None``."""
        stored = await _run(session, PlanningRunStatus.SUCCEEDED)
        loaded = await PlanningRunRepository(session).get(stored.id)

        assert loaded is not None
        assert loaded.unassigned_requirement_ids == []

    async def test_timestamps_come_back_aware(self, session: AsyncSession) -> None:
        """A stored moment is comparable to ``datetime.now(UTC)``.

        Notes:
            SQLite drops the offset where PostgreSQL keeps it, so without the
            normaliser this returns a naive value and any comparison against an
            aware one raises. The mapper is what stops that divergence.
        """
        stored = await _run(session, PlanningRunStatus.RUNNING)
        repository = PlanningRunRepository(session)
        await repository.update(
            stored.model_copy(update={"started_at": datetime.now(UTC)})
        )

        loaded = await repository.get(stored.id)
        assert loaded is not None
        assert loaded.started_at is not None
        assert loaded.started_at <= datetime.now(UTC)

    # ------------------------------------------------------------------ #
    #  Listing
    # ------------------------------------------------------------------ #

    async def test_an_absent_run_reads_as_none(self, session: AsyncSession) -> None:
        """A run that does not exist is ``None``, not an error."""
        assert await PlanningRunRepository(session).get("nope") is None

    async def test_latest_succeeded_ignores_failed_runs(
        self, session: AsyncSession
    ) -> None:
        """Only a succeeded run can be the latest one."""
        repository = PlanningRunRepository(session)
        await _run(session, PlanningRunStatus.SUCCEEDED)
        await _run(session, PlanningRunStatus.FAILED)

        latest = await repository.latest_succeeded()
        assert latest is not None
        assert latest.status is PlanningRunStatus.SUCCEEDED

    # ------------------------------------------------------------------ #
    #  Claiming a run
    # ------------------------------------------------------------------ #

    async def test_a_pending_run_can_be_claimed(self, session: AsyncSession) -> None:
        """The winner gets the run back, now running and stamped."""
        stored = await _run(session, PlanningRunStatus.PENDING)
        started = datetime.now(UTC)

        claimed = await PlanningRunRepository(session).claim(stored.id, started)

        assert claimed is not None
        assert claimed.id == stored.id
        assert claimed.status is PlanningRunStatus.RUNNING
        assert claimed.started_at is not None

    async def test_a_run_can_only_be_claimed_once(self, session: AsyncSession) -> None:
        """The second worker is told it lost, rather than solving in parallel.

        Notes:
            **This is the test the compare-and-swap exists for.** A message is
            acknowledged only once its handler returns, so a worker killed
            mid-solve leaves its run to be redelivered — and two workers holding
            it would each solve the same period and each overwrite the other's
            plan. The ``WHERE status = 'pending'`` is evaluated by the database,
            so exactly one of them can match.
        """
        stored = await _run(session, PlanningRunStatus.PENDING)
        repository = PlanningRunRepository(session)

        first = await repository.claim(stored.id, datetime.now(UTC))
        second = await repository.claim(stored.id, datetime.now(UTC))

        assert first is not None
        assert second is None

    @pytest.mark.parametrize(
        "settled",
        [
            pytest.param(PlanningRunStatus.RUNNING, id="Refused - already running"),
            pytest.param(PlanningRunStatus.SUCCEEDED, id="Refused - succeeded"),
            pytest.param(PlanningRunStatus.FAILED, id="Refused - failed"),
        ],
    )
    async def test_only_a_pending_run_can_be_claimed(
        self, session: AsyncSession, settled: PlanningRunStatus
    ) -> None:
        """A finished run redelivered by the broker is not solved again.

        Notes:
            Re-running a succeeded run would rewrite a calendar people are
            already working from, for no reason at all.
        """
        stored = await _run(session, settled)

        claimed = await PlanningRunRepository(session).claim(
            stored.id, datetime.now(UTC)
        )

        assert claimed is None

    async def test_claiming_a_run_that_is_not_there_is_reported(
        self, session: AsyncSession
    ) -> None:
        """``None``, not an error: the run may have been deleted."""
        assert (
            await PlanningRunRepository(session).claim("nope", datetime.now(UTC))
            is None
        )

    async def test_a_losing_claim_leaves_the_run_alone(
        self, session: AsyncSession
    ) -> None:
        """The loser must not stamp its own start time over the winner's.

        Notes:
            The moment matters: it is what a manager reads to know how long a
            solve has been going, and a second worker moving it forward would
            make a run that started ten minutes ago look like it just began.
        """
        stored = await _run(session, PlanningRunStatus.PENDING)
        repository = PlanningRunRepository(session)
        winner = await repository.claim(stored.id, datetime.now(UTC))

        await repository.claim(stored.id, datetime.now(UTC))

        loaded = await repository.get(stored.id)
        assert winner is not None
        assert loaded is not None
        assert loaded.started_at == winner.started_at


class TestInterventionRepository:
    """Tests for the produced plan's persistence."""

    # ------------------------------------------------------------------ #
    #  One agency's plan is not another's
    # ------------------------------------------------------------------ #

    async def test_replanning_one_agency_leaves_another_agencys_week_intact(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """The delete names an agency, so it cannot reach past one.

        Notes:
            **This is the test the whole scoping change exists for.** Replacing
            a period deletes every visit in it and writes the new plan back;
            unscoped, one agency replanning its week deleted every other
            agency's visits in the same days and wrote none of them back. Two
            agencies planning overlapping periods is the normal case, not a rare
            race — the broker gives each its own queue precisely so their runs
            proceed at the same time — so this lost calendars routinely.
        """
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)
        theirs = _visit(hca_id, run.id, name="Theirs").model_copy(
            update={"company_id": "company-2"}
        )

        await repository.replace_for_period(
            "company-2", MONDAY, date(2026, 8, 9), [theirs]
        )
        await repository.replace_for_period(
            "company-1", MONDAY, date(2026, 8, 9), [_visit(hca_id, run.id, name="Ours")]
        )

        visits = await repository.list_for_hca(hca_id, MONDAY, date(2026, 8, 9))
        assert sorted(visit.name for visit in visits) == ["Ours", "Theirs"]

    async def test_an_empty_plan_clears_only_its_own_agency(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """A run that placed nothing still must not blank everybody else.

        Notes:
            The emptiest case is the most dangerous one: with no visits to write
            back, an unscoped delete leaves nothing behind at all. It is also
            why the agency is a parameter rather than read off the visits —
            there are none to read it from.
        """
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)
        theirs = _visit(hca_id, run.id, name="Theirs").model_copy(
            update={"company_id": "company-2"}
        )
        await repository.replace_for_period(
            "company-2", MONDAY, date(2026, 8, 9), [theirs]
        )

        await repository.replace_for_period("company-1", MONDAY, date(2026, 8, 9), [])

        visits = await repository.list_for_hca(hca_id, MONDAY, date(2026, 8, 9))
        assert [visit.name for visit in visits] == ["Theirs"]

    async def test_the_agency_survives_the_round_trip(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """A stored visit still knows whose calendar it is on.

        Notes:
            It has to: the next replacement of that period finds it by exactly
            this column, and a visit that lost it would be one no run could ever
            clear.
        """
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)
        await repository.replace_for_period(
            "company-1", MONDAY, date(2026, 8, 9), [_visit(hca_id, run.id)]
        )

        visits = await repository.list_for_hca(hca_id, MONDAY, date(2026, 8, 9))
        assert [visit.company_id for visit in visits] == ["company-1"]

    # ------------------------------------------------------------------ #
    #  Replacing a period
    # ------------------------------------------------------------------ #

    async def test_replacing_a_period_swaps_its_visits(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """A second plan for the same week replaces the first."""
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)

        await repository.replace_for_period(
            "company-1",
            MONDAY,
            date(2026, 8, 9),
            [_visit(hca_id, run.id, name="First")],
        )
        await repository.replace_for_period(
            "company-1",
            MONDAY,
            date(2026, 8, 9),
            [_visit(hca_id, run.id, name="Second")],
        )

        visits = await repository.list_for_hca(hca_id, MONDAY, date(2026, 8, 9))
        assert [visit.name for visit in visits] == ["Second"]

    async def test_replacing_a_period_leaves_the_next_week_alone(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """Re-planning one week must not blank the week after it.

        Notes:
            The delete is scoped by day, not by run. A run-scoped delete would
            wipe next week too, because that week was written by the same
            earlier run.
        """
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)

        await repository.replace_for_period(
            "company-1",
            MONDAY,
            date(2026, 8, 16),
            [
                _visit(hca_id, run.id, day=MONDAY, name="This week"),
                _visit(hca_id, run.id, day=NEXT_MONDAY, name="Next week"),
            ],
        )
        await repository.replace_for_period(
            "company-1",
            MONDAY,
            date(2026, 8, 9),
            [_visit(hca_id, run.id, name="Replanned")],
        )

        visits = await repository.list_for_hca(hca_id, MONDAY, date(2026, 8, 16))
        assert [visit.name for visit in visits] == ["Replanned", "Next week"]

    async def test_an_empty_replacement_clears_the_period(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """A run that placed nothing empties the period it covered."""
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)

        await repository.replace_for_period(
            "company-1", MONDAY, date(2026, 8, 9), [_visit(hca_id, run.id)]
        )
        written = await repository.replace_for_period(
            "company-1", MONDAY, date(2026, 8, 9), []
        )

        assert written == 0
        assert await repository.count_for_period(MONDAY, date(2026, 8, 9)) == 0

    # ------------------------------------------------------------------ #
    #  Reading a diary
    # ------------------------------------------------------------------ #

    async def test_a_diary_is_ordered_by_day_then_start(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """Visits come back in the order they will be worked.

        Notes:
            A calendar rendered from an unordered list would show the afternoon
            above the morning; ordering in SQL rather than in the client keeps
            every consumer consistent.
        """
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)

        await repository.replace_for_period(
            "company-1",
            MONDAY,
            date(2026, 8, 9),
            [
                _visit(hca_id, run.id, day=TUESDAY, start=time(9, 0), name="Tue 09h"),
                _visit(hca_id, run.id, day=MONDAY, start=time(16, 0), name="Mon 16h"),
                _visit(hca_id, run.id, day=MONDAY, start=time(9, 0), name="Mon 09h"),
            ],
        )

        visits = await repository.list_for_hca(hca_id, MONDAY, date(2026, 8, 9))
        assert [visit.name for visit in visits] == ["Mon 09h", "Mon 16h", "Tue 09h"]

    async def test_a_diary_holds_only_that_assistants_visits(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """One assistant's read never returns another's work.

        Notes:
            This is the storage half of the confidentiality rule. The service
            decides *whether* a caller may read a diary; the repository decides
            *what is in it*, and a missing filter here would leak regardless of
            how well the service guards the route.
        """
        first = await _hca(session, hca_kwargs, "luc.martin@example.com")
        second = await _hca(session, hca_kwargs, "ana.lopez@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)

        await repository.replace_for_period(
            "company-1",
            MONDAY,
            date(2026, 8, 9),
            [
                _visit(first, run.id, name="Luc's"),
                _visit(second, run.id, start=time(11, 0), name="Ana's"),
            ],
        )

        visits = await repository.list_for_hca(first, MONDAY, date(2026, 8, 9))
        assert [visit.name for visit in visits] == ["Luc's"]

    async def test_a_diary_is_bounded_by_the_period(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """Work outside the requested window is not returned."""
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)

        await repository.replace_for_period(
            "company-1",
            MONDAY,
            date(2026, 8, 16),
            [
                _visit(hca_id, run.id, day=MONDAY, name="In"),
                _visit(hca_id, run.id, day=NEXT_MONDAY, name="Out"),
            ],
        )

        visits = await repository.list_for_hca(hca_id, MONDAY, date(2026, 8, 9))
        assert [visit.name for visit in visits] == ["In"]

    async def test_the_address_survives_the_round_trip(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """A visit remembers where it happened, coordinate included.

        Notes:
            The address is copied onto the visit rather than joined from the
            customer, so a customer who later moves does not rewrite history.
        """
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)

        await repository.replace_for_period(
            "company-1", MONDAY, date(2026, 8, 9), [_visit(hca_id, run.id)]
        )

        visits = await repository.list_for_hca(hca_id, MONDAY, date(2026, 8, 9))
        assert visits[0].address.city == "Paris"
        assert visits[0].address.latitude == pytest.approx(48.8566)

    # ------------------------------------------------------------------ #
    #  Cross-cutting
    # ------------------------------------------------------------------ #

    async def test_the_assistants_with_work_are_listed_once_each(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """An assistant with three visits appears once."""
        first = await _hca(session, hca_kwargs, "luc.martin@example.com")
        second = await _hca(session, hca_kwargs, "ana.lopez@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)

        await repository.replace_for_period(
            "company-1",
            MONDAY,
            date(2026, 8, 9),
            [
                _visit(first, run.id, start=time(9, 0)),
                _visit(first, run.id, start=time(11, 0)),
                _visit(second, run.id, start=time(14, 0)),
            ],
        )

        hca_ids: List[str] = await repository.list_hca_ids_for_period(
            MONDAY, date(2026, 8, 9)
        )
        assert sorted(hca_ids) == sorted([first, second])

    async def test_a_customer_s_visits_are_readable_over_a_period(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """What billing charges for: the hours actually worked, and by whom.

        Notes:
            Scoped by customer *and* by period, which is what keeps it inside
            the rule the repository sets for itself — there is deliberately no
            "every intervention" query. This is :meth:`list_for_hca` with the
            other party named.
        """
        first = await _hca(session, hca_kwargs, "luc.martin@example.com")
        second = await _hca(session, hca_kwargs, "ana.lopez@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)

        await repository.replace_for_period(
            "company-1",
            MONDAY,
            date(2026, 8, 9),
            [
                _visit(first, run.id, start=time(11, 0), name="Courses"),
                _visit(second, run.id, start=time(9, 0), name="Toilette"),
            ],
        )

        visits = await repository.list_for_customer(
            "customer-1", MONDAY, date(2026, 8, 9)
        )

        assert [visit.name for visit in visits] == ["Toilette", "Courses"]
        assert visits[0].hca_full_name == "Luc Martin"

    async def test_another_customer_s_visits_are_not_returned(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """One customer's invoice must never charge for another's care."""
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)
        await repository.replace_for_period(
            "company-1", MONDAY, date(2026, 8, 9), [_visit(hca_id, run.id)]
        )

        assert (
            await repository.list_for_customer("customer-2", MONDAY, date(2026, 8, 9))
            == []
        )

    async def test_a_customer_with_no_planned_visit_reads_as_empty(
        self, session: AsyncSession
    ) -> None:
        """A period nobody planned is empty, not an error.

        Notes:
            Billing still issues an invoice for such a period — the work was
            sold whether or not the solver ever placed it — so this has to be a
            usable answer rather than a failure.
        """
        assert (
            await InterventionRepository(session).list_for_customer(
                "customer-1", MONDAY, date(2026, 8, 9)
            )
            == []
        )

    async def test_a_visit_cannot_name_an_absent_assistant(
        self, session: AsyncSession
    ) -> None:
        """The foreign key refuses a visit for nobody.

        Notes:
            Worth pinning: a plan referencing a deleted assistant would render
            as a diary with no owner, and the failure would surface only in the
            interface.
        """
        run = await _run(session, PlanningRunStatus.RUNNING)
        with pytest.raises(IntegrityError):
            await InterventionRepository(session).replace_for_period(
                "company-1", MONDAY, date(2026, 8, 9), [_visit("ghost", run.id)]
            )

    # ------------------------------------------------------------------ #
    #  Editing one visit
    # ------------------------------------------------------------------ #

    async def test_a_visit_is_readable_by_identifier(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """The one read a caller holding a visit can make.

        Notes:
            Everything else on this repository is scoped by assistant or by
            period on purpose. This is not the "all interventions" query that
            refuses to exist: a caller who already holds an identifier was
            given it by a diary they were allowed to read.
        """
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)
        await repository.replace_for_period(
            "company-1",
            MONDAY,
            date(2026, 8, 9),
            [_visit(hca_id, run.id, name="Toilette")],
        )
        stored = (await repository.list_for_hca(hca_id, MONDAY, date(2026, 8, 9)))[0]

        found = await repository.get(stored.id or "")

        assert found is not None
        assert found.name == "Toilette"

    async def test_an_absent_visit_reads_as_none(self, session: AsyncSession) -> None:
        """Absence is a value, not an exception, at this layer."""
        assert await InterventionRepository(session).get("visit-404") is None

    async def test_a_visit_can_be_relabelled(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """Re-classifying a visit corrects the calendar in the same breath."""
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)
        await repository.replace_for_period(
            "company-1",
            MONDAY,
            date(2026, 8, 9),
            [_visit(hca_id, run.id, name="Toilette")],
        )
        stored = (await repository.list_for_hca(hca_id, MONDAY, date(2026, 8, 9)))[0]

        updated = await repository.update(
            stored.model_copy(update={"name": "Compagnie"})
        )

        assert updated is not None
        assert updated.name == "Compagnie"

    async def test_updating_a_visit_with_no_identifier_reads_as_none(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """Nothing to update, and nothing written."""
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        without_id = _visit(hca_id, run.id).model_copy(update={"id": None})

        assert await InterventionRepository(session).update(without_id) is None

    async def test_updating_an_absent_visit_reads_as_none(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """A visit deleted under the caller is not silently recreated."""
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        absent = _visit(hca_id, run.id).model_copy(update={"id": "visit-404"})

        assert await InterventionRepository(session).update(absent) is None

    async def test_a_visit_can_be_deleted(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """Cancelling one visit leaves the rest of the week standing."""
        hca_id = await _hca(session, hca_kwargs, "luc.martin@example.com")
        run = await _run(session, PlanningRunStatus.RUNNING)
        repository = InterventionRepository(session)
        await repository.replace_for_period(
            "company-1",
            MONDAY,
            date(2026, 8, 9),
            [
                _visit(hca_id, run.id, name="Cancelled"),
                _visit(hca_id, run.id, start=time(14, 0), name="Kept"),
            ],
        )
        visits = await repository.list_for_hca(hca_id, MONDAY, date(2026, 8, 9))

        assert await repository.delete(visits[0].id or "") is True

        left = await repository.list_for_hca(hca_id, MONDAY, date(2026, 8, 9))
        assert [visit.name for visit in left] == ["Kept"]

    async def test_deleting_an_absent_visit_reports_false(
        self, session: AsyncSession
    ) -> None:
        """The caller learns there was nothing there, rather than nothing."""
        assert await InterventionRepository(session).delete("visit-404") is False
