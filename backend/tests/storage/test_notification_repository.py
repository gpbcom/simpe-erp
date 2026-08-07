from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime, timedelta
from typing import List

# Third-party imports
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.auth.user import User
from models.enums import NotificationKind, UserRole
from models.notifications.notification import Notification
from storage.repositories.notifications.notification import NotificationRepository
from storage.repositories.auth.user import UserRepository


@pytest_asyncio.fixture
async def reader(session: AsyncSession) -> User:
    """Return a stored account to address notifications to.

    Args:
        session (AsyncSession): The open session.

    Returns:
        User: The account, with an identifier.

    Notes:
        A real row rather than an invented identifier, because the table
        declares ``recipient_id`` as a foreign key onto ``users`` and the test
        database enforces it.
    """
    return await UserRepository(session).create(
        User(
            company_id="company-1",
            email="claire.bernard@example.com",
            full_name="Claire Bernard",
            role=UserRole.MANAGER,
            hashed_password="$2b$12$notarealhash",
        )
    )


@pytest_asyncio.fixture
async def other_reader(session: AsyncSession) -> User:
    """Return a second stored account, to test isolation against.

    Args:
        session (AsyncSession): The open session.

    Returns:
        User: The other account.
    """
    return await UserRepository(session).create(
        User(
            company_id="company-1",
            email="paul.leroy@example.com",
            full_name="Paul Leroy",
            role=UserRole.MANAGER,
            hashed_password="$2b$12$notarealhash",
        )
    )


@pytest.fixture
def three_for(reader: User) -> List[Notification]:
    """Return three unsaved notifications for one account, oldest first.

    Args:
        reader (User): The account to address them to.

    Returns:
        List[Notification]: Three notifications an hour apart.
    """
    start = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    return [
        Notification(
            recipient_id=reader.id,
            kind=NotificationKind.QUOTE_SUBMITTED,
            title=f"Devis D-{index} à valider",
            quote_id=f"quote-{index}",
            created_at=start + timedelta(hours=index),
        )
        for index in range(3)
    ]


class TestWriting:
    """Tests for putting notifications in front of a reader."""

    async def test_a_written_notification_starts_unread(
        self, session: AsyncSession, reader: User
    ) -> None:
        """It is the unread state that raises the badge."""
        stored = await NotificationRepository(session).create(
            Notification(
                recipient_id=reader.id,
                kind=NotificationKind.QUOTE_VALIDATED,
                title="Devis D-1 validé",
                quote_id="quote-1",
            )
        )

        assert stored.id is not None
        assert stored.is_read is False
        assert stored.read_at is None

    async def test_a_fan_out_writes_one_row_per_recipient(
        self,
        session: AsyncSession,
        reader: User,
        other_reader: User,
    ) -> None:
        """A notification is per-account, not per-event.

        Notes:
            Which is what lets one supervisor clear their queue without
            clearing everybody's.
        """
        written = await NotificationRepository(session).create_many(
            [
                Notification(
                    recipient_id=recipient.id,
                    kind=NotificationKind.QUOTE_SUBMITTED,
                    title="Devis D-1 à valider",
                    quote_id="quote-1",
                )
                for recipient in (reader, other_reader)
            ]
        )

        assert [notification.recipient_id for notification in written] == [
            reader.id,
            other_reader.id,
        ]
        assert len({notification.id for notification in written}) == 2


class TestReading:
    """Tests for what a reader sees in their own queue."""

    async def test_the_newest_notification_comes_first(
        self, session: AsyncSession, reader: User, three_for: List[Notification]
    ) -> None:
        """A queue read top-down should read most-recent-first."""
        repository = NotificationRepository(session)
        await repository.create_many(three_for)

        listed = await repository.list_for(reader.id)

        assert [notification.title for notification in listed] == [
            "Devis D-2 à valider",
            "Devis D-1 à valider",
            "Devis D-0 à valider",
        ]

    async def test_a_page_is_the_size_it_was_asked_for(
        self, session: AsyncSession, reader: User, three_for: List[Notification]
    ) -> None:
        """The popover shows a page, not the whole history."""
        repository = NotificationRepository(session)
        await repository.create_many(three_for)

        first = await repository.list_for(reader.id, page=1, size=2)
        second = await repository.list_for(reader.id, page=2, size=2)

        assert len(first) == 2
        assert len(second) == 1
        assert {notification.id for notification in first}.isdisjoint(
            {notification.id for notification in second}
        )

    async def test_unread_only_hides_what_has_been_read(
        self, session: AsyncSession, reader: User, three_for: List[Notification]
    ) -> None:
        """The unread filter is what the 'unread' chip is drawn from."""
        repository = NotificationRepository(session)
        written = await repository.create_many(three_for)
        await repository.mark_read(written[0].id, reader.id)

        unread = await repository.list_for(reader.id, unread_only=True)

        assert len(unread) == 2
        assert all(notification.is_read is False for notification in unread)

    async def test_a_reader_never_sees_another_account_s_queue(
        self,
        session: AsyncSession,
        reader: User,
        other_reader: User,
        three_for: List[Notification],
    ) -> None:
        """The recipient is the credential; there is no way to name another."""
        repository = NotificationRepository(session)
        await repository.create_many(three_for)

        assert await repository.list_for(other_reader.id) == []
        assert await repository.count_unread(other_reader.id) == 0

    async def test_the_badge_counts_only_what_is_unread(
        self, session: AsyncSession, reader: User, three_for: List[Notification]
    ) -> None:
        """Counted rather than fetched-and-measured, so the badge stays cheap."""
        repository = NotificationRepository(session)
        written = await repository.create_many(three_for)

        assert await repository.count_unread(reader.id) == 3

        await repository.mark_read(written[0].id, reader.id)

        assert await repository.count_unread(reader.id) == 2


class TestMarkingRead:
    """Tests for clearing a queue."""

    async def test_marking_read_records_when(
        self, session: AsyncSession, reader: User, three_for: List[Notification]
    ) -> None:
        """A read notification stops counting and says when it stopped."""
        repository = NotificationRepository(session)
        written = await repository.create_many(three_for)

        marked = await repository.mark_read(written[0].id, reader.id)

        assert marked is not None
        assert marked.is_read is True
        assert marked.read_at is not None

    async def test_another_account_s_notification_cannot_be_marked(
        self,
        session: AsyncSession,
        reader: User,
        other_reader: User,
        three_for: List[Notification],
    ) -> None:
        """**The isolation the 404 rests on.**

        Notes:
            The recipient is part of the query rather than a check made after
            the row is loaded, so there is no moment at which somebody else's
            notification is in memory to be returned by mistake. The route turns
            this ``None`` into the same 404 it would answer for a notification
            that never existed.
        """
        repository = NotificationRepository(session)
        written = await repository.create_many(three_for)

        assert await repository.mark_read(written[0].id, other_reader.id) is None
        assert await repository.count_unread(reader.id) == 3

    async def test_an_unknown_notification_reads_as_none(
        self, session: AsyncSession, reader: User
    ) -> None:
        """Indistinguishable from one belonging to somebody else, deliberately."""
        repository = NotificationRepository(session)

        assert await repository.mark_read("no-such-id", reader.id) is None

    async def test_marking_all_read_clears_the_queue_and_says_how_many(
        self, session: AsyncSession, reader: User, three_for: List[Notification]
    ) -> None:
        """One UPDATE, whatever the size of the queue."""
        repository = NotificationRepository(session)
        await repository.create_many(three_for)

        marked = await repository.mark_all_read(reader.id)

        assert marked == 3
        assert await repository.count_unread(reader.id) == 0

    async def test_marking_all_read_leaves_other_accounts_alone(
        self,
        session: AsyncSession,
        reader: User,
        other_reader: User,
        three_for: List[Notification],
    ) -> None:
        """One reader clearing their queue must not clear anybody else's."""
        repository = NotificationRepository(session)
        await repository.create_many(three_for)
        await repository.create(
            Notification(
                recipient_id=other_reader.id,
                kind=NotificationKind.QUOTE_SUBMITTED,
                title="Devis D-9 à valider",
                quote_id="quote-9",
            )
        )

        await repository.mark_all_read(reader.id)

        assert await repository.count_unread(other_reader.id) == 1

    async def test_marking_an_empty_queue_marks_nothing(
        self, session: AsyncSession, reader: User
    ) -> None:
        """The button is disabled for this, but the call must still be safe."""
        assert await NotificationRepository(session).mark_all_read(reader.id) == 0


class TestPersistence:
    """Tests for a notification outliving the session that will read it."""

    async def test_an_unread_notification_survives_a_new_session(
        self, session: AsyncSession, reader: User, three_for: List[Notification]
    ) -> None:
        """**Signing out and signing back in must not clear the badge.**

        Notes:
            Nothing about a notification is tied to a login: it is a row keyed
            by the account, and the only thing that ends its unread life is the
            reader marking it. Re-reading through a repository built fresh
            stands in for the next sign-in, which reaches the same table through
            the same query.
        """
        await NotificationRepository(session).create_many(three_for)
        session.expunge_all()

        after_signing_back_in = NotificationRepository(session)

        assert await after_signing_back_in.count_unread(reader.id) == 3
        assert len(await after_signing_back_in.list_for(reader.id)) == 3
