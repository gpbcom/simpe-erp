from __future__ import annotations

# Standard library imports
from datetime import date, time
from decimal import Decimal
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.configuration.pricing_config import PricingConfig
from models.enums import QuoteStatus, ServiceCategory
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from service.quotes.exceptions import (
    MTQuoteForbidden,
    MTQuoteNotEditable,
    MTQuoteNotPriced,
)
from service.quotes.quotes import QuoteService

TUESDAY = date(2026, 8, 4)
AUTHOR = "user-hca-1"
OTHER_AUTHOR = "user-hca-2"
MANAGER = "user-manager-1"


def _line(priced: bool = True) -> QuoteLine:
    """Build a quote line.

    Args:
        priced (bool): Whether the line carries its computed amounts.

    Returns:
        QuoteLine: The line.
    """
    amounts = (
        {
            "hourly_rate_ht": Decimal("31.91"),
            "total_ht": Decimal("31.91"),
            "vat_amount": Decimal("1.76"),
            "total_ttc": Decimal("33.67"),
        }
        if priced
        else {}
    )
    return QuoteLine(
        name="Aide a la toilette",
        intervention_type_id="type-1",
        service_date=TUESDAY,
        earliest_start=time(9, 0),
        latest_end=time(11, 0),
        duration_minutes=60,
        **amounts,
    )


def _quote(
    status: QuoteStatus = QuoteStatus.DRAFT,
    authored_by: Optional[str] = AUTHOR,
    lines: Optional[List[QuoteLine]] = None,
) -> Quote:
    """Build a quote in a given state.

    Args:
        status (QuoteStatus): Where the quote sits in its lifecycle.
        authored_by (Optional[str]): The account that wrote it.
        lines (Optional[List[QuoteLine]]): Its lines; one priced line by
            default.

    Returns:
        Quote: The quote.
    """
    return Quote(
        id="quote-1",
        reference="D-0142",
        customer_id="customer-1",
        status=status,
        authored_by=authored_by,
        lines=lines if lines is not None else [_line()],
    )


@pytest.fixture
def quotes() -> AsyncMock:
    """Return a stand-in quote repository.

    Returns:
        AsyncMock: The repository double, echoing the quote it is given.
    """
    repository = AsyncMock()
    repository.get.return_value = _quote()
    repository.record_submission.return_value = _quote(
        status=QuoteStatus.PENDING_VALIDATION
    )
    repository.record_validation.return_value = _quote(status=QuoteStatus.SENT)
    return repository


@pytest.fixture
def service(quotes: AsyncMock) -> QuoteService:
    """Return a quote service over a stand-in store.

    Args:
        quotes (AsyncMock): The repository double.

    Returns:
        QuoteService: The service under test.
    """
    return QuoteService(
        quotes=quotes,
        types=MagicMock(),
        config=PricingConfig(),
    )


class TestQuoteSubmission:
    """Tests for an assistant submitting a quote for validation."""

    async def test_a_priced_draft_is_submitted(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """The ordinary case moves the quote into the validation queue."""
        submitted = await service.submit_for_validation("quote-1", author_id=AUTHOR)

        assert submitted.status is QuoteStatus.PENDING_VALIDATION
        quotes.record_submission.assert_awaited_once()

    async def test_another_assistants_draft_cannot_be_submitted(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """An assistant may only submit what they wrote.

        Notes:
            **This is the test the scoping rests on.** A route guard proves the
            caller is an assistant; nothing at the routing layer stops assistant
            A putting assistant B's quote identifier in the path. The comparison
            can only be made here, against the stored author.
        """
        quotes.get.return_value = _quote(authored_by=OTHER_AUTHOR)

        with pytest.raises(MTQuoteForbidden):
            await service.submit_for_validation("quote-1", author_id=AUTHOR)

        quotes.record_submission.assert_not_awaited()

    async def test_an_unpriced_draft_cannot_be_submitted(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """A quote with nothing on it must not reach a manager's queue."""
        quotes.get.return_value = _quote(lines=[])

        with pytest.raises(MTQuoteNotPriced):
            await service.submit_for_validation("quote-1", author_id=AUTHOR)

    @pytest.mark.parametrize(
        "status",
        [
            QuoteStatus.PENDING_VALIDATION,
            QuoteStatus.SENT,
            QuoteStatus.ACCEPTED,
            QuoteStatus.REJECTED,
        ],
    )
    async def test_only_a_draft_may_be_submitted(
        self, service: QuoteService, quotes: AsyncMock, status: QuoteStatus
    ) -> None:
        """Submitting anything past draft is refused.

        Args:
            service (QuoteService): The service under test.
            quotes (AsyncMock): The repository double.
            status (QuoteStatus): The state the quote is already in.
        """
        quotes.get.return_value = _quote(status=status)

        with pytest.raises(MTQuoteNotEditable):
            await service.submit_for_validation("quote-1", author_id=AUTHOR)


class TestQuoteValidation:
    """Tests for a manager ruling on a submitted quote."""

    async def test_validating_issues_the_quote(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """Approval sends the quote, and records who approved it."""
        quotes.get.return_value = _quote(status=QuoteStatus.PENDING_VALIDATION)

        validated = await service.validate("quote-1", validator_id=MANAGER)

        assert validated.status is QuoteStatus.SENT
        assert quotes.record_validation.await_args.kwargs["validated_by"] == MANAGER
        assert quotes.record_validation.await_args.kwargs["status"] is QuoteStatus.SENT

    async def test_refusing_returns_the_quote_to_its_author(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """A refused quote goes back to draft, not to rejected.

        Notes:
            ``REJECTED`` means the *customer* said no. Collapsing a manager's
            refusal into it would lose the difference between an offer the
            agency declined to make and one the family turned down — opposite
            facts about the same customer.
        """
        quotes.get.return_value = _quote(status=QuoteStatus.PENDING_VALIDATION)
        quotes.record_validation.return_value = _quote(status=QuoteStatus.DRAFT)

        returned = await service.refuse_validation("quote-1", validator_id=MANAGER)

        assert returned.status is QuoteStatus.DRAFT
        assert quotes.record_validation.await_args.kwargs["status"] is QuoteStatus.DRAFT

    @pytest.mark.parametrize(
        "status",
        [QuoteStatus.DRAFT, QuoteStatus.SENT, QuoteStatus.ACCEPTED],
    )
    async def test_only_a_submitted_quote_may_be_validated(
        self, service: QuoteService, quotes: AsyncMock, status: QuoteStatus
    ) -> None:
        """Validating something nobody submitted is refused.

        Args:
            service (QuoteService): The service under test.
            quotes (AsyncMock): The repository double.
            status (QuoteStatus): The state the quote is in.
        """
        quotes.get.return_value = _quote(status=status)

        with pytest.raises(MTQuoteNotEditable):
            await service.validate("quote-1", validator_id=MANAGER)


class TestQuoteSending:
    """Tests for the guard added to sending."""

    async def test_a_quote_awaiting_validation_cannot_be_sent(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """The validation step cannot be walked around by sending directly.

        Notes:
            Without this, ``POST /send`` would be a way for a manager to issue
            an assistant's figures without ever ruling on them — and, worse,
            leave ``validated_by`` empty on a quote that reached a customer.
        """
        quotes.get.return_value = _quote(status=QuoteStatus.PENDING_VALIDATION)

        with pytest.raises(MTQuoteNotEditable):
            await service.send("quote-1")

    async def test_an_accepted_quote_cannot_be_sent_again(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """Re-sending would overwrite the customer's answer with the offer."""
        quotes.get.return_value = _quote(status=QuoteStatus.ACCEPTED)

        with pytest.raises(MTQuoteNotEditable):
            await service.send("quote-1")

    async def test_a_priced_draft_is_still_sendable(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """The existing manager path keeps working."""
        quotes.set_status.return_value = _quote(status=QuoteStatus.SENT)

        sent = await service.send("quote-1")

        assert sent.status is QuoteStatus.SENT


class TestQuoteAuthorship:
    """Tests for who a quote is recorded against."""

    async def test_the_author_is_taken_from_the_caller(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """A payload cannot name somebody else as the author.

        Notes:
            A quote naming another account as its author would land in that
            person's list, and they would be the one a manager asks about a
            price they never set.
        """
        service.types.get_many = AsyncMock(
            return_value={
                "type-1": InterventionType(
                    id="type-1",
                    name="Aide a la toilette",
                    code="TOI",
                    service_category=ServiceCategory.NECESSITY,
                )
            }
        )
        quotes.create.return_value = _quote()

        await service.create(_quote(authored_by=OTHER_AUTHOR), author_id=AUTHOR)

        stored = quotes.create.await_args.args[0]
        assert stored.authored_by == AUTHOR
