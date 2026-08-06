from __future__ import annotations

# Standard library imports
from datetime import date, time, timedelta
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
    MTQuoteNotFound,
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
        service_category="necessity",
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
            await service.send("quote-1", validator_id=MANAGER)

    async def test_an_accepted_quote_cannot_be_sent_again(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """Re-sending would overwrite the customer's answer with the offer."""
        quotes.get.return_value = _quote(status=QuoteStatus.ACCEPTED)

        with pytest.raises(MTQuoteNotEditable):
            await service.send("quote-1", validator_id=MANAGER)

    async def test_sending_a_draft_accepts_it_so_the_planner_sees_it(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """A hand-written quote becomes schedulable the moment it goes out.

        Notes:
            The assertion that matters is ``is_schedulable``, not the status
            it happens to be spelled with: a manager writes a quote for an
            arrangement they have already settled with the family, and nothing
            else in the agency moves such a quote past ``SENT``. Left at
            ``SENT`` it fell outside :attr:`Quote.SCHEDULABLE_STATUSES` and the
            visits were promised but never planned.
        """
        quotes.record_validation.return_value = _quote(status=QuoteStatus.ACCEPTED)

        sent = await service.send("quote-1", validator_id=MANAGER)

        assert sent.status is QuoteStatus.ACCEPTED
        assert sent.is_schedulable()
        assert quotes.record_validation.await_args.kwargs["status"] is (
            QuoteStatus.ACCEPTED
        )

    async def test_sending_records_who_agreed_and_when_the_offer_lapses(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """Sending is the approval, so it is stamped like one.

        Notes:
            An issued quote carrying no issue date and no expiry is one a
            customer can hold the agency to for ever, and one whose
            ``validated_by`` cannot answer "who agreed to this price?".
        """
        quotes.record_validation.return_value = _quote(status=QuoteStatus.ACCEPTED)

        await service.send("quote-1", validator_id=MANAGER)

        recorded = quotes.record_validation.await_args.kwargs
        assert recorded["validated_by"] == MANAGER
        assert recorded["validated_at"] is not None
        assert recorded["valid_until"] == recorded["issued_on"] + timedelta(
            days=QuoteService.VALIDITY_DAYS
        )

    async def test_an_unpriced_draft_cannot_be_sent(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """Nothing reaches a customer, or the planner, without amounts.

        Notes:
            Sharper now than when sending only moved a status: an unpriced
            quote that went out would be accepted by the same call, putting
            unbilled hours on an assistant's calendar.
        """
        quotes.get.return_value = _quote(lines=[_line(priced=False)])

        with pytest.raises(MTQuoteNotPriced):
            await service.send("quote-1", validator_id=MANAGER)

        quotes.record_validation.assert_not_awaited()


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


class TestQuoteDeletion:
    """Tests for removing a quote outright.

    Notes:
        Deletion sits outside the lifecycle every other test here exercises. A
        refused quote is rejected, not erased — the agency has to be able to
        say what it offered. This is for records that were never part of that
        history: one raised in error, and the fixtures the QA campaign creates
        and is obliged to remove again.
    """

    async def test_a_quote_is_removed(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """The ordinary case deletes the row and its lines."""
        quotes.delete.return_value = True

        await service.delete("quote-1")

        quotes.delete.assert_awaited_once_with("quote-1")

    async def test_deleting_a_quote_that_is_not_there_is_reported(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """Absence is an error, not a silent success.

        Notes:
            A caller removing a fixture it believes it created wants to know
            when there was nothing to remove. Passing over it hides both a
            fixture that was never made and one something else already took.
        """
        quotes.delete.return_value = False

        with pytest.raises(MTQuoteNotFound):
            await service.delete("quote-9")


class TestQuoteEditability:
    """Tests for when a quote's lines may change.

    Notes:
        **Every status.** The rule used to be drafts only, and what that
        protected is worth stating: an issued quote is what the customer is
        looking at, so changing it underneath them is how somebody accepts one
        thing and is billed for another. Nothing records the figures an edit
        replaced, so that history is not recoverable from the quote itself.

        What did *not* widen is who may edit. The authorship check is unchanged.
    """

    @pytest.mark.parametrize(
        "status",
        list(QuoteStatus),
        ids=lambda status: status.value,
    )
    def test_every_status_is_editable(self, status: QuoteStatus) -> None:
        """A quote is modifiable wherever it has got to.

        Args:
            status (QuoteStatus): The status to check.
        """
        assert status in QuoteService.EDITABLE_STATUSES

    @pytest.mark.parametrize(
        "status",
        [
            pytest.param(QuoteStatus.SENT, id="Refused - already sent"),
            pytest.param(QuoteStatus.ACCEPTED, id="Refused - accepted"),
        ],
    )
    def test_sending_is_still_restricted_to_a_draft(self, status: QuoteStatus) -> None:
        """Editing widened; sending did not.

        Args:
            status (QuoteStatus): The status to check.

        Notes:
            Re-sending a quote the customer has already answered would overwrite
            their answer with the offer. Editing and sending are separate rules,
            and only one of them was asked to change.
        """
        assert status not in QuoteService.SENDABLE_STATUSES

    async def test_an_accepted_quote_can_have_its_lines_replaced(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """The case the old rule refused."""
        quotes.get.return_value = _quote(status=QuoteStatus.ACCEPTED)
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

        await service.replace_lines("quote-1", _quote(status=QuoteStatus.ACCEPTED))

        # `update` rather than a dedicated replace: the service prices the new
        # lines onto a copy of the stored quote and writes the whole thing.
        quotes.update.assert_awaited_once()

    async def test_editing_still_refuses_somebody_elses_quote(
        self, service: QuoteService, quotes: AsyncMock
    ) -> None:
        """Who may edit did not widen with when.

        Notes:
            The two guards are independent, and only the status one was asked to
            change. A quote landing in somebody else's list is still theirs.
        """
        quotes.get.return_value = _quote(status=QuoteStatus.ACCEPTED)

        with pytest.raises(MTQuoteForbidden):
            await service.replace_lines(
                "quote-1",
                _quote(status=QuoteStatus.ACCEPTED),
                author_id=OTHER_AUTHOR,
            )
