from __future__ import annotations

# Standard library imports
from contextlib import asynccontextmanager
from datetime import date, datetime, UTC
from typing import AsyncIterator, Dict, List, Tuple
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.billing.billing_run import BillingRun
from models.configuration.app_config import AppConfig
from models.enums import (
    BillingPeriodicity,
    BillingRunStatus,
    EventRoutingKey,
    NotificationKind,
    WorkerRole,
)
from models.messaging.event_envelope import EventEnvelope
from models.notifications.notification import Notification
from worker.runner import WorkerRunner


def an_envelope(**payload: object) -> EventEnvelope:
    """Build a broker message.

    Args:
        **payload: The fields the message carries.

    Returns:
        EventEnvelope: The message.
    """
    return EventEnvelope(routing_key="billing.run.completed", payload=dict(payload))


def a_run(
    status: BillingRunStatus = BillingRunStatus.SUCCEEDED, bills: int = 2
) -> BillingRun:
    """Build a finished generation run.

    Args:
        status (BillingRunStatus): The status it reached.
        bills (int): How many invoices it wrote.

    Returns:
        BillingRun: The run.
    """
    return BillingRun(
        id="run-1",
        company_id="company-1",
        status=status,
        reference_date=date(2026, 4, 1),
        periodicity=BillingPeriodicity.MONTHLY,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        bill_ids=[f"bill-{index}" for index in range(bills)],
        requested_at=datetime.now(UTC),
    )


@pytest.fixture
def published() -> List[Tuple[EventRoutingKey, str, Dict[str, object]]]:
    """Collect what the runner announces.

    Returns:
        List[Tuple[EventRoutingKey, str, Dict[str, object]]]: The routing key,
        agency and payload of every publish.
    """
    return []


@pytest.fixture
def notified() -> List[Notification]:
    """Collect the notifications the runner writes.

    Returns:
        List[Notification]: The notifications.
    """
    return []


@pytest.fixture
def announced() -> List[str]:
    """Collect the invoices handed to the billing webhook.

    Returns:
        List[str]: The identifiers announced.
    """
    return []


@pytest.fixture
def runner(
    monkeypatch: pytest.MonkeyPatch,
    published: List[Tuple[EventRoutingKey, str, Dict[str, object]]],
    notified: List[Notification],
    announced: List[str],
) -> WorkerRunner:
    """Return a runner reaching neither a database, a broker nor a mailer.

    Args:
        monkeypatch (pytest.MonkeyPatch): Replaces every I/O seam.
        published (List[Tuple[EventRoutingKey, str, Dict[str, object]]]): Where
            announcements are collected.
        notified (List[Notification]): Where notifications are collected.
        announced (List[str]): Where webhook announcements are collected.

    Returns:
        WorkerRunner: The runner under test.
    """
    built = WorkerRunner(config=AppConfig(), role=WorkerRole.BILLING)

    @asynccontextmanager
    async def _session() -> AsyncIterator[object]:
        """Yield a stand-in session.

        Yields:
            object: A placeholder the recording stores ignore.
        """
        yield object()

    monkeypatch.setattr(built.manager, "session", _session)
    monkeypatch.setattr(
        built.publisher,
        "publish",
        AsyncMock(
            side_effect=lambda key, company_id, payload: published.append(
                (key, company_id, payload)
            )
        ),
    )
    monkeypatch.setattr(
        built.billing_webhook,
        "announce",
        AsyncMock(side_effect=lambda bill_id: announced.append(bill_id)),
    )

    async def _notify(
        session: object,
        company_id: str,
        kind: NotificationKind,
        title: str,
        body: str,
        quote_id: object = None,
    ) -> List[str]:
        """Record a supervisor notification instead of writing one.

        Args:
            session (object): The stand-in session.
            company_id (str): The agency told.
            kind (NotificationKind): What it is about.
            title (str): The heading.
            body (str): The text.
            quote_id (object): Unused here.

        Returns:
            List[str]: The recipients, stubbed.
        """
        notified.append(
            Notification(recipient_id="manager-1", kind=kind, title=title, body=body)
        )
        return ["manager-1"]

    monkeypatch.setattr(built, "_notify_supervisors", _notify)
    monkeypatch.setattr(built, "_announce", AsyncMock(return_value=None))
    return built


class TestRunningAGeneration:
    """Tests for the handler that actually writes the invoices."""

    async def test_a_finished_run_announces_its_completion(
        self,
        runner: WorkerRunner,
        monkeypatch: pytest.MonkeyPatch,
        published: List[Tuple[EventRoutingKey, str, Dict[str, object]]],
    ) -> None:
        """The agency has to hear that a month is ready to validate.

        Args:
            runner (WorkerRunner): The worker under test.
            monkeypatch (pytest.MonkeyPatch): Replaces the service.
            published (List[...]): Where announcements are collected.
        """
        service = AsyncMock()
        service.execute_run = AsyncMock(return_value=a_run())
        monkeypatch.setattr(runner, "_billing_service", lambda session: service)

        await runner.run_billing(an_envelope(run_id="run-1", company_id="company-1"))

        assert published[0][0] is EventRoutingKey.BILLING_RUN_COMPLETED
        assert published[0][1] == "company-1"
        assert published[0][2]["bill_count"] == 2

    async def test_a_message_naming_no_run_is_dropped(
        self, runner: WorkerRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nothing to execute, so nothing is attempted.

        Args:
            runner (WorkerRunner): The worker under test.
            monkeypatch (pytest.MonkeyPatch): Replaces the service.
        """
        service = AsyncMock()
        monkeypatch.setattr(runner, "_billing_service", lambda session: service)

        await runner.run_billing(an_envelope(company_id="company-1"))

        service.execute_run.assert_not_awaited()

    async def test_a_run_naming_no_agency_is_not_announced(
        self,
        runner: WorkerRunner,
        monkeypatch: pytest.MonkeyPatch,
        published: List[Tuple[EventRoutingKey, str, Dict[str, object]]],
    ) -> None:
        """**A routing key cannot be scoped to nobody.**

        Args:
            runner (WorkerRunner): The worker under test.
            monkeypatch (pytest.MonkeyPatch): Replaces the service.
            published (List[...]): Where announcements are collected.

        Notes:
            The invoices are written either way — the work is done and
            committed. What is dropped is the announcement, because a key with
            an empty agency binds to nothing and would look like a quiet
            success.
        """
        service = AsyncMock()
        service.execute_run = AsyncMock(return_value=a_run())
        monkeypatch.setattr(runner, "_billing_service", lambda session: service)

        await runner.run_billing(an_envelope(run_id="run-1"))

        service.execute_run.assert_awaited_once()
        assert published == []


class TestTellingTheAgency:
    """Tests for the notification a finished run raises."""

    async def test_a_successful_run_is_announced_to_supervisors(
        self, runner: WorkerRunner, notified: List[Notification]
    ) -> None:
        """**Unlike a planning run, where success is deliberately silent.**

        Args:
            runner (WorkerRunner): The worker under test.
            notified (List[Notification]): Where notifications are collected.

        Notes:
            A planning rewrites calendars everybody can see. A billing run
            leaves invoices nobody has approved and nothing has been sent from,
            so a run nobody hears about is a month quietly unbilled.
        """
        await runner.billing_completed(
            an_envelope(
                run_id="run-1",
                status=BillingRunStatus.SUCCEEDED.value,
                company_id="company-1",
                bill_count="12",
            )
        )

        assert len(notified) == 1
        assert notified[0].kind is NotificationKind.BILLS_TO_VALIDATE
        assert "12" in notified[0].body

    async def test_the_notification_says_nothing_has_been_sent(
        self, runner: WorkerRunner, notified: List[Notification]
    ) -> None:
        """So a manager knows the customers have heard nothing yet.

        Args:
            runner (WorkerRunner): The worker under test.
            notified (List[Notification]): Where notifications are collected.
        """
        await runner.billing_completed(
            an_envelope(
                run_id="run-1",
                status=BillingRunStatus.SUCCEEDED.value,
                company_id="company-1",
                bill_count="3",
            )
        )

        assert "bénéficiaires" in notified[0].body

    async def test_a_failed_run_says_no_invoice_was_issued(
        self, runner: WorkerRunner, notified: List[Notification]
    ) -> None:
        """The one thing a manager needs to know to act on it.

        Args:
            runner (WorkerRunner): The worker under test.
            notified (List[Notification]): Where notifications are collected.
        """
        await runner.billing_completed(
            an_envelope(
                run_id="run-1",
                status=BillingRunStatus.FAILED.value,
                company_id="company-1",
            )
        )

        assert "Échec" in notified[0].title

    async def test_nothing_is_emailed_to_a_customer_here(
        self, runner: WorkerRunner, announced: List[str]
    ) -> None:
        """**Generating and sending are separate steps.**

        Args:
            runner (WorkerRunner): The worker under test.
            announced (List[str]): Where webhook announcements are collected.

        Notes:
            The run tells the agency it has invoices to look at. A customer
            hears only after a manager approves one, which is the whole point
            of generating them at ``to-be-validated``.
        """
        await runner.billing_completed(
            an_envelope(
                run_id="run-1",
                status=BillingRunStatus.SUCCEEDED.value,
                company_id="company-1",
                bill_count="3",
            )
        )

        assert announced == []


class TestSendingAnApprovedInvoice:
    """Tests for the handler that reaches a customer."""

    async def test_an_approved_invoice_is_handed_to_the_webhook(
        self, runner: WorkerRunner, announced: List[str]
    ) -> None:
        """**This is the step that puts a document in an inbox.**

        Args:
            runner (WorkerRunner): The worker under test.
            announced (List[str]): Where webhook announcements are collected.

        Notes:
            Handed to the webhook rather than sent here, so the delivery runs as
            an ordinary authenticated request with the same handlers and logging
            as everything else — the arrangement the planning dispatch already
            has.
        """
        await runner.bill_accepted(an_envelope(bill_id="bill-1"))

        assert announced == ["bill-1"]

    async def test_a_message_naming_no_invoice_is_dropped(
        self, runner: WorkerRunner, announced: List[str]
    ) -> None:
        """There is nothing to send and nobody to send it to.

        Args:
            runner (WorkerRunner): The worker under test.
            announced (List[str]): Where webhook announcements are collected.
        """
        await runner.bill_accepted(an_envelope(company_id="company-1"))

        assert announced == []


class TestTheQueueTopology:
    """Tests that the billing role binds its own queue and only its own."""

    async def test_the_billing_role_binds_only_the_billing_queue(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**A queue bound with no handler quietly drops its work.**

        Args:
            monkeypatch (pytest.MonkeyPatch): Records the bindings.

        Notes:
            A consumer with no handler for a routing key acknowledges the
            message and discards it. Binding another role's queue would
            therefore not fail — it would silently swallow that role's work.
        """
        built = WorkerRunner(config=AppConfig(), role=WorkerRole.BILLING)
        bound: List[Tuple[str, str]] = []
        for name in ("planning", "notifications", "billing"):
            consumer = getattr(built, name)
            monkeypatch.setattr(
                consumer,
                "consume_for_company",
                AsyncMock(
                    side_effect=lambda queue, keys, company_id, tag=name: (
                        bound.append((tag, queue))
                    )
                ),
            )

        await built.serve("company-1")

        assert bound == [("billing", "billing-runs")]

    def test_readiness_asks_this_role_s_own_consumer(self) -> None:
        """A worker whose connection has gone consumes nothing.

        Notes:
            The other consumers hold no connection by design, so asking all
            three would report every worker unready for ever.
        """
        built = WorkerRunner(config=AppConfig(), role=WorkerRole.BILLING)

        assert built.is_ready() is False
