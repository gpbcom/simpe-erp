from __future__ import annotations

# Standard library imports
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.configuration.app_config import AppConfig
from models.enums import EventRoutingKey, NotificationKind, UserRole
from models.messaging.event_envelope import EventEnvelope
from models.notifications.notification import Notification
from worker.runner import WorkerRunner


def supervisor(identifier: str) -> User:
    """Return a stored manager account.

    Args:
        identifier (str): The account's identifier.

    Returns:
        User: A manager belonging to ``company-1``.
    """
    return User(
        id=identifier,
        company_id="company-1",
        email=f"{identifier}@example.com",
        full_name=identifier.replace("-", " ").title(),
        role=UserRole.MANAGER,
        hashed_password="$2b$12$notarealhash",
    )


class RecordingRepositories:
    """The stores a handler reaches for, recording rather than writing.

    Attributes:
        supervisors (Dict[Optional[str], List[User]]): Who answers
            ``list_supervisors`` for each agency asked about.
        asked_for (List[Optional[str]]): Every agency ``list_supervisors`` was
            called with, in order.
        written (List[Notification]): Every notification handed to a store.

    Notes:
        The repositories are constructed inside the handler, from the session it
        opens, so they cannot be injected. Patching the classes on the module
        under test is what lets the handler run its real logic — resolving
        recipients, building the models, deciding whether to announce — against
        a store that only remembers.
    """

    def __init__(self, supervisors: Dict[Optional[str], List[User]]) -> None:
        """Initialize the stand-ins.

        Args:
            supervisors (Dict[Optional[str], List[User]]): The roster, keyed by
                the agency that will be asked about.
        """
        self.supervisors = supervisors
        self.asked_for: List[Optional[str]] = []
        self.written: List[Notification] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Replace the repository classes the runner builds.

        Args:
            monkeypatch (pytest.MonkeyPatch): Used to swap the classes.
        """
        monkeypatch.setattr("worker.runner.UserRepository", self._users)
        monkeypatch.setattr("worker.runner.NotificationRepository", self._notifications)

    def _users(self, session=None, logger=None) -> AsyncMock:
        """Return a stand-in account store.

        Args:
            session: Ignored.
            logger: Ignored.

        Returns:
            AsyncMock: A store answering ``list_supervisors``.
        """
        store = AsyncMock()
        store.list_supervisors = AsyncMock(side_effect=self._list_supervisors)
        return store

    async def _list_supervisors(self, company_id: Optional[str]) -> List[User]:
        """Answer with the roster for one agency.

        Args:
            company_id (Optional[str]): The agency asked about.

        Returns:
            List[User]: Its supervisors, or none.
        """
        self.asked_for.append(company_id)
        return self.supervisors.get(company_id, [])

    def _notifications(self, session=None, logger=None) -> AsyncMock:
        """Return a stand-in notification store.

        Args:
            session: Ignored.
            logger: Ignored.

        Returns:
            AsyncMock: A store recording what it is asked to write.
        """
        store = AsyncMock()
        store.create_many = AsyncMock(side_effect=self._create_many)
        store.create = AsyncMock(side_effect=self._create)
        return store

    async def _create_many(
        self, notifications: List[Notification]
    ) -> List[Notification]:
        """Record a fan-out.

        Args:
            notifications (List[Notification]): What to write.

        Returns:
            List[Notification]: The same notifications, as written.
        """
        self.written.extend(notifications)
        return list(notifications)

    async def _create(self, notification: Notification) -> Notification:
        """Record a single write.

        Args:
            notification (Notification): What to write.

        Returns:
            Notification: The same notification, as written.
        """
        self.written.append(notification)
        return notification


@pytest.fixture
def published() -> List[Tuple[EventRoutingKey, str, dict]]:
    """Collect what the runner announces.

    Returns:
        List[Tuple[EventRoutingKey, str, dict]]: The routing key, agency and
        payload of every publish.
    """
    return []


@pytest.fixture
def runner(
    monkeypatch: pytest.MonkeyPatch,
    published: List[Tuple[EventRoutingKey, str, dict]],
) -> WorkerRunner:
    """Return a runner whose session and publisher are stand-ins.

    Args:
        monkeypatch (pytest.MonkeyPatch): Used to replace the pool and the
            publisher.
        published (List[Tuple[EventRoutingKey, str, dict]]): Where announcements
            are collected.

    Returns:
        WorkerRunner: A runner that reaches neither a database nor a broker.
    """
    built = WorkerRunner(config=AppConfig())

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
    return built


class TestQuoteSubmitted:
    """Tests for telling an agency's supervisors that a quote needs ruling on."""

    async def test_one_notification_is_written_per_supervisor(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
    ) -> None:
        """Managers **and** administrators, each with their own row."""
        stores = RecordingRepositories(
            {"company-1": [supervisor("manager-1"), supervisor("admin-1")]}
        )
        stores.install(monkeypatch)

        await runner.quote_submitted(
            EventEnvelope(
                routing_key="quote.submitted",
                payload={
                    "quote_id": "quote-1",
                    "reference": "D-42",
                    "company_id": "company-1",
                    "author_name": "Luc Martin",
                },
            )
        )

        assert [written.recipient_id for written in stores.written] == [
            "manager-1",
            "admin-1",
        ]
        assert stores.written[0].kind is NotificationKind.QUOTE_SUBMITTED
        assert stores.written[0].title == "Devis D-42 à valider"
        assert stores.written[0].quote_id == "quote-1"

    async def test_the_recipients_are_announced_to_the_api(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
        published: List[Tuple[EventRoutingKey, str, dict]],
    ) -> None:
        """**This is what turns a written row into a live badge.**

        Notes:
            Identifiers only. The reader fetches the notifications themselves
            over HTTP, so the message stays small and the database stays the one
            place a notification lives.
        """
        stores = RecordingRepositories(
            {"company-1": [supervisor("manager-1"), supervisor("admin-1")]}
        )
        stores.install(monkeypatch)

        await runner.quote_submitted(
            EventEnvelope(
                routing_key="quote.submitted",
                payload={
                    "quote_id": "quote-1",
                    "reference": "D-42",
                    "company_id": "company-1",
                },
            )
        )

        assert published == [
            (
                EventRoutingKey.NOTIFICATION_CREATED,
                "company-1",
                {"recipient_ids": ["manager-1", "admin-1"]},
            )
        ]

    async def test_an_agency_with_no_supervisor_announces_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
        published: List[Tuple[EventRoutingKey, str, dict]],
    ) -> None:
        """Nothing was written, so there is nobody to wake."""
        stores = RecordingRepositories({})
        stores.install(monkeypatch)

        await runner.quote_submitted(
            EventEnvelope(
                routing_key="quote.submitted",
                payload={"quote_id": "quote-1", "company_id": "company-1"},
            )
        )

        assert stores.written == []
        assert published == []

    async def test_a_broker_that_refuses_the_announcement_is_survivable(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
    ) -> None:
        """**The row is already committed; only the push was lost.**

        Notes:
            Raising here would dead-letter the message and hand it to the next
            worker, which would write the notification a second time. A reader
            seeing a duplicate is a worse outcome than one seeing it a moment
            late.
        """
        stores = RecordingRepositories({"company-1": [supervisor("manager-1")]})
        stores.install(monkeypatch)
        monkeypatch.setattr(runner.publisher, "publish", AsyncMock(return_value=False))

        await runner.quote_submitted(
            EventEnvelope(
                routing_key="quote.submitted",
                payload={"quote_id": "quote-1", "company_id": "company-1"},
            )
        )

        assert len(stores.written) == 1


class TestQuoteRuledOn:
    """Tests for telling an assistant what became of the quote they wrote."""

    async def test_the_author_is_told_it_was_validated(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
        published: List[Tuple[EventRoutingKey, str, dict]],
    ) -> None:
        """The return leg of the workflow."""
        stores = RecordingRepositories({})
        stores.install(monkeypatch)

        await runner.quote_validated(
            EventEnvelope(
                routing_key="quote.validated",
                payload={
                    "quote_id": "quote-1",
                    "reference": "D-42",
                    "author_id": "assistant-1",
                    "company_id": "company-1",
                },
            )
        )

        assert len(stores.written) == 1
        assert stores.written[0].recipient_id == "assistant-1"
        assert stores.written[0].kind is NotificationKind.QUOTE_VALIDATED
        assert stores.written[0].title == "Devis D-42 validé"
        assert published == [
            (
                EventRoutingKey.NOTIFICATION_CREATED,
                "company-1",
                {"recipient_ids": ["assistant-1"]},
            )
        ]

    async def test_the_author_is_told_it_came_back(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
    ) -> None:
        """Refused is not rejected: it goes back to be corrected."""
        stores = RecordingRepositories({})
        stores.install(monkeypatch)

        await runner.quote_refused(
            EventEnvelope(
                routing_key="quote.refused",
                payload={
                    "quote_id": "quote-1",
                    "reference": "D-42",
                    "author_id": "assistant-1",
                    "company_id": "company-1",
                },
            )
        )

        assert stores.written[0].kind is NotificationKind.QUOTE_REFUSED
        assert stores.written[0].title == "Devis D-42 à corriger"

    async def test_a_quote_with_no_recorded_author_tells_nobody(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
        published: List[Tuple[EventRoutingKey, str, dict]],
    ) -> None:
        """Those exist — written before authorship was recorded."""
        stores = RecordingRepositories({})
        stores.install(monkeypatch)

        await runner.quote_validated(
            EventEnvelope(
                routing_key="quote.validated",
                payload={"quote_id": "quote-1", "company_id": "company-1"},
            )
        )

        assert stores.written == []
        assert published == []


class TestPlanningCompleted:
    """Tests for what a finished planning run tells whom."""

    async def test_a_succeeded_run_notifies_nobody_and_calls_the_dispatcher(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
        published: List[Tuple[EventRoutingKey, str, dict]],
    ) -> None:
        """Telling managers about every routine run trains them to ignore the badge.

        Notes:
            The webhook is the point of a successful run: it is what emails
            every assistant their diary and every customer their quote.
        """
        stores = RecordingRepositories({"company-1": [supervisor("manager-1")]})
        stores.install(monkeypatch)
        announce = AsyncMock()
        monkeypatch.setattr(runner.webhook, "announce", announce)

        await runner.planning_completed(
            EventEnvelope(
                routing_key="planning.run.completed",
                payload={
                    "run_id": "run-1",
                    "status": "succeeded",
                    "company_id": "company-1",
                },
            )
        )

        assert stores.written == []
        assert published == []
        announce.assert_awaited_once_with("run-1")

    async def test_a_failed_run_tells_only_its_own_agency(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
        published: List[Tuple[EventRoutingKey, str, dict]],
    ) -> None:
        """**The cross-tenant regression.**

        Notes:
            This handler used to pass ``company_id=None``, and
            ``list_supervisors(None)`` means *every* supervisor of *every*
            agency. A failed run in one agency therefore put a badge on every
            other agency's managers, naming a run they have no access to. The
            agency now travels in the payload, and the assertion below is that
            it is the one asked about.
        """
        stores = RecordingRepositories(
            {
                "company-1": [supervisor("manager-1")],
                None: [supervisor("manager-1"), supervisor("manager-elsewhere")],
            }
        )
        stores.install(monkeypatch)

        await runner.planning_completed(
            EventEnvelope(
                routing_key="planning.run.completed",
                payload={
                    "run_id": "run-1",
                    "status": "failed",
                    "company_id": "company-1",
                },
            )
        )

        assert stores.asked_for == ["company-1"]
        assert [written.recipient_id for written in stores.written] == ["manager-1"]
        assert published == [
            (
                EventRoutingKey.NOTIFICATION_CREATED,
                "company-1",
                {"recipient_ids": ["manager-1"]},
            )
        ]

    async def test_a_failed_run_naming_no_agency_notifies_nobody(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
        published: List[Tuple[EventRoutingKey, str, dict]],
    ) -> None:
        """A message from an older publisher must not fan out platform-wide.

        Notes:
            The account store reads a missing agency as "every supervisor of
            every agency", so the absence is refused before it is ever asked —
            nothing is written, and there is nothing to announce.
        """
        stores = RecordingRepositories(
            {None: [supervisor("manager-1"), supervisor("manager-elsewhere")]}
        )
        stores.install(monkeypatch)

        await runner.planning_completed(
            EventEnvelope(
                routing_key="planning.run.completed",
                payload={"run_id": "run-1", "status": "failed"},
            )
        )

        assert stores.asked_for == []
        assert stores.written == []
        assert published == []


class TestSkillAdded:
    """Tests for telling the supervisors that an assistant declared a skill."""

    async def test_every_supervisor_is_told(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
    ) -> None:
        """**This is what makes a declaration needing no approval safe.**

        Notes:
            A skill takes effect the moment its owner enters it, which is what
            stops the agency losing track of who can do what. The safeguard is
            that every manager and administrator is told, and any of them can
            withdraw it before the next planning run acts on it.
        """
        stores = RecordingRepositories(
            {"company-1": [supervisor("manager-1"), supervisor("admin-1")]}
        )
        stores.install(monkeypatch)

        await runner.skill_added(
            EventEnvelope(
                routing_key="skill.added",
                payload={
                    "hca_id": "hca-1",
                    "hca_name": "Luc Martin",
                    "skill_name": "Leve-personne",
                    "skill_code": "LEVE-PERSONNE",
                    "company_id": "company-1",
                },
            )
        )

        assert [written.recipient_id for written in stores.written] == [
            "manager-1",
            "admin-1",
        ]
        assert stores.written[0].kind is NotificationKind.SKILL_ADDED
        assert "Luc Martin" in stores.written[0].title

    async def test_the_body_names_the_code_as_well_as_the_label(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
    ) -> None:
        """The code is what a requirement is matched on.

        Notes:
            A supervisor deciding whether somebody has over-claimed needs to
            know which requirement the declaration just satisfied, and the
            free-text name does not say.
        """
        stores = RecordingRepositories({"company-1": [supervisor("manager-1")]})
        stores.install(monkeypatch)

        await runner.skill_added(
            EventEnvelope(
                routing_key="skill.added",
                payload={
                    "hca_name": "Luc Martin",
                    "skill_name": "Leve-personne",
                    "skill_code": "LEVE-PERSONNE",
                    "company_id": "company-1",
                },
            )
        )

        assert "LEVE-PERSONNE" in (stores.written[0].body or "")

    async def test_the_notification_points_at_no_quote(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
    ) -> None:
        """There is no quote, so the row renders as text rather than a link.

        Notes:
            This is why ``concerns_a_quote`` had to stop being written as "not
            the planning one": a skill notification rendered as a link would be
            a dead one.
        """
        stores = RecordingRepositories({"company-1": [supervisor("manager-1")]})
        stores.install(monkeypatch)

        await runner.skill_added(
            EventEnvelope(
                routing_key="skill.added",
                payload={"skill_name": "x", "company_id": "company-1"},
            )
        )

        assert stores.written[0].quote_id is None
        assert stores.written[0].is_actionable() is False

    async def test_the_recipients_are_announced_to_the_api(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
        published: List[Tuple[EventRoutingKey, str, dict]],
    ) -> None:
        """The badge lights the same way it does for a submitted quote."""
        stores = RecordingRepositories({"company-1": [supervisor("manager-1")]})
        stores.install(monkeypatch)

        await runner.skill_added(
            EventEnvelope(
                routing_key="skill.added",
                payload={"skill_name": "x", "company_id": "company-1"},
            )
        )

        assert published == [
            (
                EventRoutingKey.NOTIFICATION_CREATED,
                "company-1",
                {"recipient_ids": ["manager-1"]},
            )
        ]

    async def test_a_message_with_no_agency_writes_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: WorkerRunner,
        published: List[Tuple[EventRoutingKey, str, dict]],
    ) -> None:
        """There is no notification worth sending to every agency at once.

        Notes:
            The account store reads a missing agency as "every supervisor of
            every agency", which would put a badge on every manager on the
            platform naming somebody they have no access to.
        """
        stores = RecordingRepositories({"company-1": [supervisor("manager-1")]})
        stores.install(monkeypatch)

        await runner.skill_added(
            EventEnvelope(routing_key="skill.added", payload={"skill_name": "x"})
        )

        assert stores.written == []
        assert published == []
