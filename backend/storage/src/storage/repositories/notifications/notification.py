from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import List, Optional, Sequence, Tuple

# Third-party imports
from sqlalchemy import Select, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.notifications.notification import Notification
from models.schemas.requests.notifications.notification_filter import (
    NotificationFilter,
)
from storage.mappers.notifications.notification_mapper import (
    NotificationMapper,  # noqa: E501
)
from storage.orm.notifications.notification_row import NotificationRow
from storage.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[NotificationRow]):
    """Reads and writes the notifications addressed to each account.

    Attributes:
        mapper (NotificationMapper): Converts between rows and models.

    Notes:
        Every read is scoped by recipient, and there is deliberately no method
        that reads a notification by identifier alone. A notification is
        addressed to one person. A lookup that did not take the reader would be
        a way to read somebody else's queue by guessing an identifier.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        super().__init__(
            session=session,
            row_class=NotificationRow,
        )
        self.mapper = NotificationMapper()

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_query(
        self,
        recipient_id: str,
        unread_only: bool = False,
        notification_filter: Optional[NotificationFilter] = None,
    ) -> Select[Tuple[NotificationRow]]:
        """Build the filtered select shared by the read methods.

        Args:
            recipient_id (str): The account whose queue is being read.
            unread_only (bool): Restrict to notifications not yet read.
            notification_filter (Optional[NotificationFilter]): The screen's
                filter. Its ``is_read`` wins over ``unread_only``.

        Returns:
            Select: The filtered statement, without ordering or pagination.

        Notes:
            **The recipient is a parameter, never a filter field.** It comes
            from the caller's own credential, and no amount of care in the
            endpoint would matter if this method could be asked for somebody
            else's queue — so the narrowing is applied here first and the
            filter has no way to name a recipient at all.
        """
        applied = notification_filter or NotificationFilter()
        self.logger.debug(
            "Building the notification query for %s from %s.",
            recipient_id,
            applied.model_dump(exclude_none=True),
        )
        statement = select(NotificationRow).where(
            NotificationRow.recipient_id == recipient_id
        )
        if applied.is_read is not None:
            if unread_only and applied.is_read:
                self.logger.warning(
                    "unread_only asked for the unread notifications and the "
                    "filter asked for the read ones. The filter wins."
                )
            statement = statement.where(NotificationRow.is_read.is_(applied.is_read))
        elif unread_only:
            statement = statement.where(NotificationRow.is_read.is_(False))
        else:
            self.logger.info("Listing every notification for %s.", recipient_id)
        if applied.kind is not None:
            statement = statement.where(NotificationRow.kind == applied.kind.value)
        if applied.search:
            pattern = f"%{applied.search.strip().lower()}%"
            statement = statement.where(
                or_(
                    NotificationRow.title.ilike(pattern),
                    NotificationRow.body.ilike(pattern),
                )
            )
        return statement

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, notification: Notification) -> Notification:
        """Store one notification.

        Args:
            notification (Notification): The notification to store.

        Returns:
            Notification: The stored notification, carrying its identifier.
        """
        row = self.mapper.to_row(notification)
        self.session.add(row)
        await self.session.flush()
        self.logger.info(
            "Notified %s: %s.", notification.recipient_id, notification.title
        )
        return self.mapper.to_model(row)

    async def create_many(
        self, notifications: Sequence[Notification]
    ) -> List[Notification]:
        """Store a fan-out of notifications in one round trip.

        Args:
            notifications (Sequence[Notification]): The notifications to store.

        Returns:
            List[Notification]: The stored notifications.

        Notes:
            One event usually reaches several managers, and adding the rows one
            statement at a time would cost a round trip each. They are flushed
            together so the whole fan-out is one transaction: either everybody
            who should have been told was, or nobody was and the caller sees the
            failure.
        """
        if not notifications:
            self.logger.debug("No notification to store.")
            return []
        rows = [self.mapper.to_row(item) for item in notifications]
        self.session.add_all(rows)
        await self.session.flush()
        self.logger.info("Stored %d notification(s).", len(rows))
        return self.mapper.to_models(rows)

    async def list(
        self,
        recipient_id: str,
        page: int = 1,
        size: Optional[int] = None,
        unread_only: bool = False,
        notification_filter: Optional[NotificationFilter] = None,
    ) -> List[Notification]:
        """Return a page of one account's notifications, newest first.

        Args:
            recipient_id (str): The account whose queue is being read.
            page (int): One-based page number.
            size (Optional[int]): Page size.
            unread_only (bool): Restrict to notifications not yet read.
            notification_filter (Optional[NotificationFilter]): The
                screen's filter.

        Returns:
            List[Notification]: The matching notifications.
        """
        self.logger.debug(
            "Listing notifications for %s: page=%d unread_only=%s.",
            recipient_id,
            page,
            unread_only,
        )
        statement = self._build_query(
            recipient_id, unread_only, notification_filter
        ).order_by(NotificationRow.created_at.desc())
        rows = await self._fetch_all(self._paginate(statement, page, size))
        if not rows:
            self.logger.debug("Account %s has no notification.", recipient_id)
        return self.mapper.to_models(rows)

    async def count_unread(self, recipient_id: str) -> int:
        """Return how many notifications an account has not read.

        Args:
            recipient_id (str): The account whose queue is being counted.

        Returns:
            int: The number of unread notifications.

        Notes:
            This is the badge. It is a count rather than the length of a fetched
            page, so a reader with four hundred unread rows costs one aggregate
            rather than four hundred mapped models.
        """
        return await self._count(self._build_query(recipient_id, unread_only=True))  # noqa: E501

    async def mark_read(
        self, notification_id: str, recipient_id: str
    ) -> Optional[Notification]:
        """Mark one notification read, if it belongs to the reader.

        Args:
            notification_id (str): The notification to mark.
            recipient_id (str): The account claiming it.

        Returns:
            Optional[Notification]: The updated notification, or ``None`` when
            it does not exist or is addressed to somebody else.

        Notes:
            The recipient is part of the **query**, not a check performed after
            the row is loaded. The two are equivalent here, but writing it this
            way means there is no moment at which another account's notification
            is in memory to be returned by mistake.
        """
        statement = select(NotificationRow).where(
            NotificationRow.id == notification_id,
            NotificationRow.recipient_id == recipient_id,
        )
        row = await self._fetch_one(statement)
        if row is None:
            self.logger.warning(
                "Account %s tried to read notification %s, which is not theirs "
                "or does not exist.",
                recipient_id,
                notification_id,
            )
            return None
        if row.is_read:
            self.logger.debug("Notification %s was already read.", notification_id)  # noqa: E501
            return self.mapper.to_model(row)
        row.is_read = True
        row.read_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(row)
        self.logger.info("Notification %s marked read.", notification_id)
        return self.mapper.to_model(row)

    async def mark_all_read(self, recipient_id: str) -> int:
        """Mark every unread notification of an account as read.

        Args:
            recipient_id (str): The account clearing their queue.

        Returns:
            int: How many notifications were marked.

        Notes:
            Issued as one ``UPDATE`` rather than a read-modify-write loop.
            Clearing a queue of several hundred is a single click, and it should
            not become several hundred statements.
        """
        now = datetime.now(UTC)
        statement = (
            update(NotificationRow)
            .where(
                NotificationRow.recipient_id == recipient_id,
                NotificationRow.is_read.is_(False),
            )
            .values(is_read=True, read_at=now, updated_at=now)
        )
        result = await self.session.execute(statement)
        await self.session.flush()
        marked = int(result.rowcount or 0)
        self.logger.info("Account %s cleared %d notification(s).", recipient_id, marked)  # noqa: E501
        return marked
