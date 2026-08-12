from __future__ import annotations

# Standard library imports
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Dict

# Third-party imports
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import QuoteStatus, ServiceCategory
from models.catalog.intervention_type import InterventionType
from models.people.customer import Customer
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from storage.repositories.catalog.intervention_type import InterventionTypeRepository
from storage.repositories.people.customer import CustomerRepository
from storage.repositories.quoting.quote import QuoteRepository
from tests.annotations import ModelInput

COMPANY = "company-1"
SERVICE_DAY = date(2026, 8, 11)
PERIOD_START = date(2026, 8, 10)
PERIOD_END = date(2026, 8, 16)


async def _customer(session: AsyncSession) -> str:
    """Store a customer and return its identifier.

    Args:
        session (AsyncSession): The open session.

    Returns:
        str: The stored customer's identifier.
    """
    stored = await CustomerRepository(session).create(
        Customer(
            first_name="Marie",
            last_name="Durand",
            phone_number="+33612345678",
            email="marie.durand@example.com",
            address={
                "street": "12 rue de Rivoli",
                "postal_code": "75004",
                "city": "Paris",
                "latitude": 48.8566,
                "longitude": 2.3522,
            },
        )
    )
    return stored.id or ""


async def _intervention_type(session: AsyncSession) -> str:
    """Store the catalogue entry the line bills against.

    Args:
        session (AsyncSession): The open session.

    Returns:
        str: The stored type's identifier.
    """
    stored = await InterventionTypeRepository(session).create(
        InterventionType(
            name="Aide a la toilette",
            code="TOILETTE",
            service_category=ServiceCategory.NECESSITY,
        )
    )
    return stored.id or ""


def _priced_line(type_id: str) -> Dict[str, ModelInput]:
    """Return a priced quote line inside the planning period.

    Args:
        type_id (str): The catalogue entry it bills against.

    Returns:
        Dict[str, ModelInput]: Constructor keywords for the line.
    """
    return {
        "name": "Aide a la toilette",
        "intervention_type_id": type_id,
        "service_category": ServiceCategory.NECESSITY,
        "service_date": SERVICE_DAY,
        "earliest_start": time(9, 0),
        "latest_end": time(12, 0),
        "duration_minutes": 60,
        "hourly_rate_ht": Decimal("31.905"),
        "total_ht": Decimal("31.91"),
        "vat_amount": Decimal("1.76"),
        "total_ttc": Decimal("33.67"),
    }


async def _submitted_quote(session: AsyncSession) -> Quote:
    """Store a quote sitting in the validation queue, as the GUI leaves it.

    Args:
        session (AsyncSession): The open session.

    Returns:
        Quote: The stored quote.
    """
    return await QuoteRepository(session).create(
        Quote(
            company_id=COMPANY,
            reference="D-0001",
            customer_id=await _customer(session),
            status=QuoteStatus.PENDING_VALIDATION,
            authored_by="user-1",
            lines=[QuoteLine(**_priced_line(await _intervention_type(session)))],
        )
    )


class TestAValidatedQuoteReachesThePlanner:
    """Tests the whole chain a quote walks from the validation queue to a run.

    Notes:
        **Every step of this is a separate write, and the planner reads the
        result of all of them.** A quote is submitted, validated — which issues
        it and moves it to ``sent`` — and only then accepted, which is the one
        status the planner will load. Anything dropped along the way surfaces
        as "the quote I validated was not taken into account", with nothing on
        any screen explaining which step lost it.

        These walk the real repository against a real session, so a column that
        stops being written fails here rather than in a planning run.
    """

    async def test_validating_makes_the_quote_schedulable(
        self, session: AsyncSession
    ) -> None:
        """**The whole reported chain, in one write.**

        Notes:
            Validation records ``accepted`` — the one status
            ``list_schedulable`` loads — so a manager approving an assistant's
            quote commits its work in the same act. It stopped at ``sent``
            before, needing a second acceptance nothing asked for.
        """
        repository = QuoteRepository(session)
        quote = await _submitted_quote(session)

        validated = await repository.record_validation(
            quote.id or "",
            status=QuoteStatus.ACCEPTED,
            validated_by="manager-1",
            validated_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
            issued_on=date(2026, 8, 7),
            valid_until=date(2026, 9, 6),
        )

        assert validated is not None
        assert validated.status is QuoteStatus.ACCEPTED
        assert validated.is_schedulable() is True
        loaded = await repository.list_schedulable(
            COMPANY, None, PERIOD_START, PERIOD_END
        )
        assert [item.reference for item in loaded] == ["D-0001"]

    async def test_a_quote_already_stored_as_sent_can_still_be_accepted(
        self, session: AsyncSession
    ) -> None:
        """The path that keeps existing ``sent`` rows reachable.

        Notes:
            No path produces ``sent`` any more, but rows stored in it before
            the change still exist. The interface keeps its tab and its accept
            button for exactly them, and this is the write behind that button.
        """
        repository = QuoteRepository(session)
        quote = await _submitted_quote(session)
        await repository.set_status(quote.id or "", QuoteStatus.SENT)

        accepted = await repository.set_status(quote.id or "", QuoteStatus.ACCEPTED)

        assert accepted is not None
        assert accepted.is_schedulable() is True
        loaded = await repository.list_schedulable(
            COMPANY, None, PERIOD_START, PERIOD_END
        )
        assert [item.reference for item in loaded] == ["D-0001"]

    async def test_validation_does_not_lose_the_agency(
        self, session: AsyncSession
    ) -> None:
        """The scoping the planner filters on must survive every write.

        Notes:
            ``list_schedulable`` is scoped to one agency, so a quote whose
            ``company_id`` were cleared by a status write would vanish from
            every run while still looking perfectly accepted on screen.
        """
        repository = QuoteRepository(session)
        quote = await _submitted_quote(session)

        await repository.record_validation(
            quote.id or "",
            status=QuoteStatus.ACCEPTED,
            validated_by="manager-1",
            validated_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
            issued_on=date(2026, 8, 7),
            valid_until=date(2026, 9, 6),
        )
        accepted = await repository.set_status(quote.id or "", QuoteStatus.ACCEPTED)

        assert accepted is not None
        assert accepted.company_id == COMPANY

    async def test_validation_does_not_lose_the_pricing(
        self, session: AsyncSession
    ) -> None:
        """An unpriced quote is not schedulable however accepted it looks."""
        repository = QuoteRepository(session)
        quote = await _submitted_quote(session)

        await repository.record_validation(
            quote.id or "",
            status=QuoteStatus.ACCEPTED,
            validated_by="manager-1",
            validated_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
            issued_on=date(2026, 8, 7),
            valid_until=date(2026, 9, 6),
        )
        accepted = await repository.set_status(quote.id or "", QuoteStatus.ACCEPTED)

        assert accepted is not None
        assert accepted.is_priced() is True
        assert accepted.lines[0].total_ttc == Decimal("33.67")

    async def test_another_agency_s_accepted_quote_is_not_loaded(
        self, session: AsyncSession
    ) -> None:
        """The scoping works in the direction that matters too."""
        repository = QuoteRepository(session)
        quote = await _submitted_quote(session)
        await repository.set_status(quote.id or "", QuoteStatus.ACCEPTED)

        assert (
            await repository.list_schedulable(
                "another-company", None, PERIOD_START, PERIOD_END
            )
            == []
        )

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            pytest.param(
                date(2026, 8, 1), date(2026, 8, 9), id="period ends too early"
            ),
            pytest.param(
                date(2026, 8, 12), date(2026, 8, 20), id="period starts too late"
            ),
        ],
    )
    async def test_a_period_that_misses_the_line_loads_nothing(
        self, session: AsyncSession, start: date, end: date
    ) -> None:
        """The filter is on the line's date, not the quote's issue date.

        Args:
            session (AsyncSession): The open session.
            start (date): First day of the window.
            end (date): Last day of the window.

        Notes:
            The most ordinary reason an accepted quote is "not taken into
            account": its work simply falls outside the week being planned.
            Worth pinning, because it is indistinguishable on screen from the
            quote having been lost.
        """
        repository = QuoteRepository(session)
        quote = await _submitted_quote(session)
        await repository.set_status(quote.id or "", QuoteStatus.ACCEPTED)

        assert await repository.list_schedulable(COMPANY, None, start, end) == []


class TestTheWorkloadIsHandedOverInAStableOrder:
    """Tests that two identical runs build the solver the identical model.

    Notes:
        **The requirement list is built by walking these rows**, so their order
        is the order of the CP-SAT variables. PostgreSQL guarantees no ordering
        for a ``SELECT`` without an ``ORDER BY``, so the same week could be
        handed to the solver as two different models — and a fixed
        ``random_seed`` with a deterministic budget then stops somewhere else
        and leaves a different number of visits unplaced.

        That is not theoretical: the same week, run twice against the same
        data, reported two unplaced visits and then one. Determinism work on
        the solver cannot hold while its input order is free to move.
    """

    async def test_the_same_query_returns_the_same_order(
        self, session: AsyncSession
    ) -> None:
        """Repeating the query must not repeat it differently."""
        repository = QuoteRepository(session)
        customer = await _customer(session)
        type_id = await _intervention_type(session)
        for index in range(8):
            await repository.create(
                Quote(
                    company_id=COMPANY,
                    reference=f"D-{index:04d}",
                    customer_id=customer,
                    status=QuoteStatus.ACCEPTED,
                    authored_by="user-1",
                    lines=[QuoteLine(**_priced_line(type_id))],
                )
            )

        runs = [
            [
                quote.id
                for quote in await repository.list_schedulable(
                    COMPANY, None, PERIOD_START, PERIOD_END
                )
            ]
            for _ in range(5)
        ]

        assert all(order == runs[0] for order in runs)

    async def test_the_order_is_total_rather_than_merely_grouped(
        self, session: AsyncSession
    ) -> None:
        """Ordering by a column with ties leaves the tied rows free to swap.

        Notes:
            Every quote here shares a customer, a status and a service date, so
            any order built on those would be arbitrary among them. The primary
            key is the only column certain to break every tie.
        """
        repository = QuoteRepository(session)
        customer = await _customer(session)
        type_id = await _intervention_type(session)
        for index in range(5):
            await repository.create(
                Quote(
                    company_id=COMPANY,
                    reference=f"D-{index:04d}",
                    customer_id=customer,
                    status=QuoteStatus.ACCEPTED,
                    authored_by="user-1",
                    lines=[QuoteLine(**_priced_line(type_id))],
                )
            )

        loaded = await repository.list_schedulable(
            COMPANY, None, PERIOD_START, PERIOD_END
        )
        identifiers = [quote.id for quote in loaded]

        assert identifiers == sorted(identifiers)
        assert len(set(identifiers)) == len(identifiers)
