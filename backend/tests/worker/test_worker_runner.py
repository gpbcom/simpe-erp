from __future__ import annotations

# Standard library imports
from typing import List
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.configuration.app_config import AppConfig
from models.messaging.event_envelope import EventEnvelope
from worker.runner import WorkerRunner


@pytest.fixture
def runner() -> WorkerRunner:
    """Return a worker that has been constructed but never connected.

    Returns:
        WorkerRunner: A runner over the default configuration, whose broker is
        disabled and whose consumers hold no connection.

    Notes:
        Nothing in ``__init__`` reaches the network: the publisher connects
        lazily, the consumers connect in ``start()``, and the pool connects when
        the first session is asked for. That is what makes the wiring testable
        without a broker or a database.
    """
    return WorkerRunner(config=AppConfig())


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, runner: WorkerRunner) -> List[str]:
    """Record the order in which a started worker touches its dependencies.

    Args:
        monkeypatch (pytest.MonkeyPatch): Used to replace every I/O call.
        runner (WorkerRunner): The worker under test.

    Returns:
        List[str]: The call log, appended to as the worker starts and stops.

    Notes:
        Ordering is the thing worth pinning here, not the calls themselves. A
        consumer started before the pool is connected delivers messages to
        handlers that have no database, and the worker then looks healthy while
        dead-lettering everything it receives.
    """
    log: List[str] = []

    def record(name: str) -> AsyncMock:
        """Return a coroutine mock that notes it was called.

        Args:
            name (str): The label to append to the log.

        Returns:
            AsyncMock: The stand-in.
        """
        return AsyncMock(side_effect=lambda *_, **__: log.append(name))

    monkeypatch.setattr(runner.manager, "connect", record("manager.connect"))
    monkeypatch.setattr(runner.manager, "disconnect", record("manager.disconnect"))
    monkeypatch.setattr(runner.publisher, "close", record("publisher.close"))
    for name in ("planning", "notifications", "lifecycle"):
        consumer = getattr(runner, name)
        monkeypatch.setattr(consumer, "start", record(f"{name}.start"))
        monkeypatch.setattr(consumer, "close", record(f"{name}.close"))
        monkeypatch.setattr(
            consumer, "consume_for_company", record(f"{name}.consume_for_company")
        )
        monkeypatch.setattr(
            consumer, "consume_every_company", record(f"{name}.consume_every_company")
        )
    monkeypatch.setattr(
        runner,
        "companies",
        AsyncMock(side_effect=lambda: (log.append("companies"), ["company-1"])[1]),
    )
    return log


class TestHandlerRegistration:
    """Tests for which coroutine answers which topic."""

    def test_every_topic_is_bound_to_the_coroutine_that_answers_it(
        self, runner: WorkerRunner
    ) -> None:
        """The wiring a queue's traffic depends on.

        Notes:
            Asserted on the handler's ``__name__`` rather than on identity,
            because a routing key bound to the wrong coroutine does not fail —
            it quietly does the wrong work, or none at all, which looks exactly
            like a quiet system.
        """
        runner._register_handlers()

        assert {
            key: handler.__name__ for key, handler in runner.planning.handlers.items()
        } == {"planning.run.requested": "run_planning"}
        assert {
            key: handler.__name__
            for key, handler in runner.notifications.handlers.items()
        } == {
            "quote.submitted": "quote_submitted",
            "quote.validated": "quote_validated",
            "quote.refused": "quote_refused",
            "planning.run.completed": "planning_completed",
        }
        assert {
            key: handler.__name__ for key, handler in runner.lifecycle.handlers.items()
        } == {"company.created": "company_created"}

    def test_the_notification_queue_binds_every_key_it_handles(
        self, runner: WorkerRunner
    ) -> None:
        """A handled topic nothing binds is a handler that never runs."""
        runner._register_handlers()

        bound = {key.value for key in runner.NOTIFICATION_KEYS}

        assert bound == set(runner.notifications.handlers)


class TestStartup:
    """Tests for the order a worker brings itself up in."""

    async def test_the_pool_is_connected_before_any_consumer_starts(
        self, runner: WorkerRunner, calls: List[str]
    ) -> None:
        """Otherwise every message is handled with no database behind it."""
        await runner.start()

        assert calls[0] == "manager.connect"
        assert calls.index("manager.connect") < calls.index("planning.start")
        assert calls.index("manager.connect") < calls.index("notifications.start")
        assert calls.index("manager.connect") < calls.index("lifecycle.start")

    async def test_the_announcement_queue_is_bound_before_agencies_are_enumerated(
        self, runner: WorkerRunner, calls: List[str]
    ) -> None:
        """An agency founded between the two must not fall through the gap.

        Notes:
            Overlapping the two is safe because :meth:`WorkerRunner.serve` is
            idempotent; leaving a gap is not.
        """
        await runner.start()

        assert calls.index("lifecycle.consume_every_company") < calls.index("companies")

    async def test_every_stored_agency_is_served(
        self, runner: WorkerRunner, calls: List[str]
    ) -> None:
        """A worker that was down while agencies were founded catches up."""
        served = await runner.start()

        assert served == ["company-1"]
        assert "planning.consume_for_company" in calls
        assert "notifications.consume_for_company" in calls


class TestShutdown:
    """Tests for the order a worker releases what it holds."""

    async def test_the_consumers_close_before_the_publisher_and_the_pool(
        self, runner: WorkerRunner, calls: List[str]
    ) -> None:
        """Nothing may still be delivering when the database goes."""
        await runner.close()

        assert calls == [
            "lifecycle.close",
            "planning.close",
            "notifications.close",
            "publisher.close",
            "manager.disconnect",
        ]


class TestAgencyAnnouncement:
    """Tests for binding an agency founded while the worker runs."""

    async def test_an_announced_agency_has_its_queues_bound(
        self, monkeypatch: pytest.MonkeyPatch, runner: WorkerRunner
    ) -> None:
        """Without this a self-registered agency is served only after a restart."""
        serve = AsyncMock()
        monkeypatch.setattr(runner, "serve", serve)

        await runner.company_created(
            EventEnvelope(
                routing_key="company.created", payload={"company_id": "company-9"}
            )
        )

        serve.assert_awaited_once_with("company-9")

    async def test_an_announcement_naming_no_agency_binds_nothing(
        self, monkeypatch: pytest.MonkeyPatch, runner: WorkerRunner
    ) -> None:
        """There is no agency to serve, and guessing one would serve the wrong."""
        serve = AsyncMock()
        monkeypatch.setattr(runner, "serve", serve)

        await runner.company_created(
            EventEnvelope(routing_key="company.created", payload={})
        )

        serve.assert_not_awaited()
