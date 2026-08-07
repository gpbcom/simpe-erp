from __future__ import annotations

# Standard library imports
from datetime import date, time
from decimal import Decimal
from typing import Any, Dict, List

# Third-party imports
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.enums import QuoteStatus, ServiceCategory
from models.people.customer import Customer
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from models.quoting.quote_type_week_aggregate import QuoteTypeWeekAggregate
from storage.repositories.people.customer import CustomerRepository
from storage.repositories.catalog.intervention_type import InterventionTypeRepository
from storage.repositories.quoting.quote import QuoteRepository

TUESDAY = date(2026, 8, 4)
NEXT_WEEK = date(2026, 8, 11)


async def _customer(session: AsyncSession, kwargs: Dict[str, Any]) -> str:
    """Store a customer and return its identifier.

    Args:
        session (AsyncSession): The open session.
        kwargs (Dict[str, Any]): Customer constructor arguments.

    Returns:
        str: The stored customer's identifier.
    """
    stored = await CustomerRepository(session).create(Customer(**kwargs))
    return stored.id


async def _intervention_type(session: AsyncSession, code: str = "TOILETTE") -> str:
    """Store an intervention type and return its identifier.

    Args:
        session (AsyncSession): The open session.
        code (str): The catalog code to assign.

    Returns:
        str: The stored type's identifier.
    """
    stored = await InterventionTypeRepository(session).create(
        InterventionType(
            name=f"Service {code}",
            code=code,
            service_category=ServiceCategory.NECESSITY,
        )
    )
    return stored.id


def _line(
    type_id: str,
    service_date: date = TUESDAY,
    name: str = "Toilette matin",
    category: str = "necessity",
) -> QuoteLine:
    """Build a priced two-hour quote line.

    Args:
        type_id (str): The intervention type it sells.
        service_date (date): The day it is delivered.
        name (str): What the service is.
        category (str): Which VAT rate the line is billed at.

    Returns:
        QuoteLine: The priced line.
    """
    return QuoteLine(
        name=name,
        intervention_type_id=type_id,
        service_category=category,
        service_date=service_date,
        earliest_start=time(9, 0),
        latest_end=time(13, 0),
        duration_minutes=120,
        hourly_rate_ht=Decimal("31.91"),
        total_ht=Decimal("63.81"),
        vat_amount=Decimal("3.51"),
        total_ttc=Decimal("67.32"),
    )


def _aggregate(type_id: str, iso_week: int = 32) -> QuoteTypeWeekAggregate:
    """Build a weekly aggregate matching one line.

    Args:
        type_id (str): The type it covers.
        iso_week (int): The ISO week number.

    Returns:
        QuoteTypeWeekAggregate: The aggregate.
    """
    return QuoteTypeWeekAggregate(
        intervention_type_id=type_id,
        service_category="necessity",
        intervention_type_name="Service TOILETTE",
        iso_year=2026,
        iso_week=iso_week,
        week_start_date=date(2026, 8, 3),
        line_count=1,
        total_minutes=120,
        total_ht=Decimal("63.81"),
        vat_amount=Decimal("3.51"),
        total_ttc=Decimal("67.32"),
    )


def _quote(
    customer_id: str,
    lines: List[QuoteLine],
    aggregates: List[QuoteTypeWeekAggregate],
    reference: str = "Q-2026-001",
    status: QuoteStatus = QuoteStatus.DRAFT,
    company_id: str = "company-1",
) -> Quote:
    """Build a quote around its lines and aggregates.

    Args:
        customer_id (str): The customer it is addressed to.
        lines (List[QuoteLine]): Its lines.
        aggregates (List[QuoteTypeWeekAggregate]): Its weekly totals.
        reference (str): The quote number.
        status (QuoteStatus): Its lifecycle status.
        company_id (str): The agency offering the work.

    Returns:
        Quote: The quote.
    """
    return Quote(
        company_id=company_id,
        reference=reference,
        customer_id=customer_id,
        status=status,
        lines=lines,
        aggregates=aggregates,
    )


class TestQuoteRepository:
    """Tests for the QuoteRepository."""

    # ------------------------------------------------------------------ #
    #  Round trip across three tables
    # ------------------------------------------------------------------ #

    async def test_a_quote_round_trips_whole(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """The header, its lines and its aggregates are written and read together."""
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)

        stored = await repository.create(
            _quote(customer_id, [_line(type_id)], [_aggregate(type_id)])
        )
        loaded = await repository.get(stored.id)

        assert loaded is not None
        assert loaded.reference == "Q-2026-001"
        assert len(loaded.lines) == 1
        assert len(loaded.aggregates) == 1
        assert loaded.lines[0].name == "Toilette matin"

    async def test_the_vat_category_survives_the_round_trip(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """**A line comes back taxed the way it was written.**

        Notes:
            The category lives on the line, not on the catalog entry it sells,
            so the row and the mapper both have to carry it. A mapper that
            dropped it would rebuild every line as ``necessity`` — and because
            the amounts are *stored*, the mismatch would not show as a wrong
            total until something repriced the quote.

            Asserted with ``comfort``, which is not the value a dropped field
            would default to. Asserting ``necessity`` would pass either way.
        """
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)

        stored = await repository.create(
            _quote(customer_id, [_line(type_id, category="comfort")], [])
        )
        loaded = await repository.get(stored.id)

        assert loaded is not None
        assert loaded.lines[0].service_category is ServiceCategory.COMFORT

    async def test_two_lines_on_one_quote_can_be_taxed_differently(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """The same catalog entry, two customers' arrangements, two rates.

        Notes:
            This is the shape the field was moved for, and it is only storable
            because the category sits on the line. Both lines sell the same
            service.
        """
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)

        stored = await repository.create(
            _quote(
                customer_id,
                [
                    _line(type_id, category="necessity", name="Sous plan d'aide"),
                    _line(type_id, category="comfort", name="A titre prive"),
                ],
                [],
            )
        )
        loaded = await repository.get(stored.id)

        assert loaded is not None
        assert [line.service_category for line in loaded.lines] == [
            ServiceCategory.NECESSITY,
            ServiceCategory.COMFORT,
        ]

    async def test_the_stored_amounts_survive_exactly(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """Money comes back as the same Decimal, to the cent.

        Notes:
            A quote must reprint identically, so the amounts are stored rather
            than recomputed. That is only worth anything if they round-trip.
        """
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)

        stored = await repository.create(
            _quote(customer_id, [_line(type_id)], [_aggregate(type_id)])
        )
        loaded = await repository.get(stored.id)

        assert loaded is not None
        assert loaded.lines[0].total_ht == Decimal("63.81")
        assert loaded.lines[0].vat_amount == Decimal("3.51")
        assert loaded.total_ttc() == Decimal("67.32")

    async def test_line_order_is_preserved(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """A quote is a document; the operator's order is what prints.

        Notes:
            Without an explicit position column the database is free to return
            the lines in any order, which silently reshuffles the document.
        """
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)

        names = ["Third", "First", "Second"]
        stored = await repository.create(
            _quote(
                customer_id,
                [_line(type_id, name=name) for name in names],
                [_aggregate(type_id)],
            )
        )
        loaded = await repository.get(stored.id)

        assert loaded is not None
        assert [line.name for line in loaded.lines] == names

    async def test_get_returns_none_for_an_unknown_id(
        self, session: AsyncSession
    ) -> None:
        """An absent quote reads as None."""
        assert await QuoteRepository(session).get("no-such-id") is None

    async def test_lookup_by_reference_is_case_insensitive(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """The model upper-cases the reference, so lookups match either way."""
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)
        await repository.create(
            _quote(customer_id, [_line(type_id)], [_aggregate(type_id)])
        )
        assert await repository.get_by_reference("q-2026-001") is not None

    # ------------------------------------------------------------------ #
    #  Constraints
    # ------------------------------------------------------------------ #

    async def test_the_reference_is_unique(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """Two quotes cannot share a number."""
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)
        await repository.create(
            _quote(customer_id, [_line(type_id)], [_aggregate(type_id)])
        )
        with pytest.raises(IntegrityError):
            await repository.create(
                _quote(customer_id, [_line(type_id)], [_aggregate(type_id)])
            )

    async def test_a_customer_with_quotes_cannot_be_deleted(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """Deleting a quoted customer would erase commercial history.

        Notes:
            The foreign key restricts rather than cascades, so removing the
            customer is a deliberate act that must deal with the quotes first.
        """
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        await QuoteRepository(session).create(
            _quote(customer_id, [_line(type_id)], [_aggregate(type_id)])
        )
        with pytest.raises(IntegrityError):
            await CustomerRepository(session).delete(customer_id)

    # ------------------------------------------------------------------ #
    #  Repricing replaces children
    # ------------------------------------------------------------------ #

    async def test_updating_replaces_the_lines_wholesale(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """Re-pricing a quote drops the lines that went away."""
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)

        stored = await repository.create(
            _quote(
                customer_id,
                [_line(type_id, name="Old A"), _line(type_id, name="Old B")],
                [_aggregate(type_id)],
            )
        )
        await repository.update(
            stored.model_copy(update={"lines": [_line(type_id, name="New")]})
        )
        reloaded = await repository.get(stored.id)

        assert reloaded is not None
        assert [line.name for line in reloaded.lines] == ["New"]

    async def test_a_line_keeps_its_identifier_across_a_reprice(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """A line the customer has seen is not renumbered by repricing."""
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)

        stored = await repository.create(
            _quote(customer_id, [_line(type_id)], [_aggregate(type_id)])
        )
        original_line_id = stored.lines[0].id
        repriced = stored.model_copy(
            update={
                "lines": [
                    stored.lines[0].model_copy(update={"total_ht": Decimal("70.00")})
                ]
            }
        )
        await repository.update(repriced)
        reloaded = await repository.get(stored.id)

        assert reloaded is not None
        assert reloaded.lines[0].id == original_line_id
        assert reloaded.lines[0].total_ht == Decimal("70.00")

    # ------------------------------------------------------------------ #
    #  Status transitions
    # ------------------------------------------------------------------ #

    async def test_set_status_leaves_the_lines_alone(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """Accepting a quote must not be able to change what was accepted."""
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)

        stored = await repository.create(
            _quote(customer_id, [_line(type_id)], [_aggregate(type_id)])
        )
        accepted = await repository.set_status(stored.id, QuoteStatus.ACCEPTED)

        assert accepted is not None
        assert accepted.status is QuoteStatus.ACCEPTED
        assert len(accepted.lines) == 1
        assert accepted.lines[0].total_ht == Decimal("63.81")

    # ------------------------------------------------------------------ #
    #  The planner's query
    # ------------------------------------------------------------------ #

    async def test_only_accepted_quotes_are_schedulable(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """A draft is still being composed and must not reach the planner."""
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)

        await repository.create(
            _quote(
                customer_id,
                [_line(type_id)],
                [_aggregate(type_id)],
                reference="Q-DRAFT",
            )
        )
        accepted = await repository.create(
            _quote(
                customer_id,
                [_line(type_id)],
                [_aggregate(type_id)],
                reference="Q-ACCEPTED",
                status=QuoteStatus.ACCEPTED,
            )
        )
        schedulable = await repository.list_schedulable(
            "company-1", date(2026, 8, 1), date(2026, 8, 31)
        )
        assert [quote.id for quote in schedulable] == [accepted.id]

    async def test_only_the_asking_agencys_work_is_schedulable(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """Another agency's accepted quote is not this agency's workload.

        Notes:
            **This is the input half of the scoping change**, and it matters as
            much as the output half. Unscoped, a run would build one agency's
            week out of every agency's accepted work — handing those visits to
            its own assistants, who have never met the customers and are not
            insured to attend them — and then write the result over everybody's
            calendar.
        """
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)
        ours = await repository.create(
            _quote(
                customer_id,
                [_line(type_id)],
                [_aggregate(type_id)],
                reference="Q-OURS",
                status=QuoteStatus.ACCEPTED,
            )
        )
        await repository.create(
            _quote(
                customer_id,
                [_line(type_id)],
                [_aggregate(type_id)],
                reference="Q-THEIRS",
                status=QuoteStatus.ACCEPTED,
                company_id="company-2",
            )
        )

        schedulable = await repository.list_schedulable(
            "company-1", date(2026, 8, 1), date(2026, 8, 31)
        )

        assert [quote.id for quote in schedulable] == [ours.id]

    async def test_an_agency_with_no_accepted_work_schedules_nothing(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """A quiet agency reads as quiet, however busy its neighbours are."""
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)
        await repository.create(
            _quote(
                customer_id,
                [_line(type_id)],
                [_aggregate(type_id)],
                reference="Q-THEIRS",
                status=QuoteStatus.ACCEPTED,
                company_id="company-2",
            )
        )

        assert (
            await repository.list_schedulable(
                "company-7", date(2026, 8, 1), date(2026, 8, 31)
            )
            == []
        )

    async def test_the_agency_survives_the_round_trip(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """A stored quote still knows which agency offered the work."""
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)
        stored = await repository.create(
            _quote(customer_id, [_line(type_id)], [_aggregate(type_id)])
        )

        loaded = await repository.get(stored.id)

        assert loaded is not None
        assert loaded.company_id == "company-1"

    async def test_the_window_filters_on_line_dates(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """A quote is schedulable when its *work* falls in the window.

        Notes:
            Filtering on the quote's issue date instead would miss a January
            quote carrying March work.
        """
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)

        await repository.create(
            _quote(
                customer_id,
                [_line(type_id, service_date=NEXT_WEEK)],
                [_aggregate(type_id, iso_week=33)],
                reference="Q-LATER",
                status=QuoteStatus.ACCEPTED,
            )
        )
        assert (
            await repository.list_schedulable(
                "company-1", date(2026, 8, 1), date(2026, 8, 7)
            )
            == []
        )
        assert (
            len(
                await repository.list_schedulable(
                    "company-1", date(2026, 8, 10), date(2026, 8, 14)
                )
            )
            == 1
        )

    async def test_a_quote_appears_once_however_many_lines_match(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """The join must not multiply the quote by its matching lines."""
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)

        await repository.create(
            _quote(
                customer_id,
                [_line(type_id), _line(type_id, name="Second"), _line(type_id)],
                [_aggregate(type_id)],
                reference="Q-MANY",
                status=QuoteStatus.ACCEPTED,
            )
        )
        assert (
            len(
                await repository.list_schedulable(
                    "company-1", date(2026, 8, 1), date(2026, 8, 31)
                )
            )
            == 1
        )

    async def test_an_empty_window_returns_nothing(self, session: AsyncSession) -> None:
        """No accepted work is an empty list, not an error."""
        assert (
            await QuoteRepository(session).list_schedulable(
                "company-1", date(2026, 8, 1), date(2026, 8, 31)
            )
            == []
        )

    # ------------------------------------------------------------------ #
    #  Listing and deletion
    # ------------------------------------------------------------------ #

    async def test_the_customer_filter_restricts_the_page(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """A customer screen shows only that customer's quotes."""
        first = await _customer(session, customer_kwargs)
        second = await _customer(
            session,
            {**customer_kwargs, "email": "other@example.com", "last_name": "Autre"},
        )
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)

        await repository.create(
            _quote(first, [_line(type_id)], [_aggregate(type_id)], reference="Q-A")
        )
        await repository.create(
            _quote(second, [_line(type_id)], [_aggregate(type_id)], reference="Q-B")
        )
        listed = await repository.list(customer_id=second)
        assert [quote.reference for quote in listed] == ["Q-B"]

    async def test_deleting_a_quote_takes_its_lines_and_aggregates(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """Both children cascade; neither has meaning without the quote."""
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)

        stored = await repository.create(
            _quote(customer_id, [_line(type_id)], [_aggregate(type_id)])
        )
        assert await repository.delete(stored.id) is True
        assert await repository.get(stored.id) is None

    async def test_an_intervention_type_in_use_cannot_be_deleted(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """A type referenced by a quote line is protected by the schema.

        Notes:
            This is what makes "retire, never delete" a rule the database
            enforces rather than a convention the service remembers.
        """
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        await QuoteRepository(session).create(
            _quote(customer_id, [_line(type_id)], [_aggregate(type_id)])
        )
        # Third-party imports
        from sqlalchemy import delete

        # First-party imports
        from storage.orm.catalog.intervention_type_row import InterventionTypeRow

        with pytest.raises(IntegrityError):
            await session.execute(
                delete(InterventionTypeRow).where(InterventionTypeRow.id == type_id)
            )
            await session.flush()

    # ------------------------------------------------------------------ #
    #  Finding a quote from one of its lines
    # ------------------------------------------------------------------ #

    async def test_a_quote_is_findable_by_one_of_its_lines(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """The lookup a scheduled visit needs.

        Notes:
            A visit knows which line produced it and nothing else about the
            paperwork. Without this, editing a visit could change the calendar
            and never touch the bill.
        """
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)
        stored = await repository.create(
            _quote(customer_id, [_line(type_id)], [_aggregate(type_id)])
        )

        found = await repository.get_by_line(stored.lines[0].id or "")

        assert found is not None
        assert found.id == stored.id

    async def test_the_whole_quote_comes_back_not_the_line(
        self, session: AsyncSession, customer_kwargs: Dict[str, Any]
    ) -> None:
        """A quote always travels whole, however it was looked up."""
        customer_id = await _customer(session, customer_kwargs)
        type_id = await _intervention_type(session)
        repository = QuoteRepository(session)
        stored = await repository.create(
            _quote(
                customer_id,
                [_line(type_id), _line(type_id, name="Repas")],
                [_aggregate(type_id)],
            )
        )

        found = await repository.get_by_line(stored.lines[0].id or "")

        assert found is not None
        assert len(found.lines) == 2
        assert len(found.aggregates) == 1

    async def test_an_unknown_line_reads_as_none(self, session: AsyncSession) -> None:
        """Absence is a value, not an exception, at this layer."""
        assert await QuoteRepository(session).get_by_line("line-404") is None
