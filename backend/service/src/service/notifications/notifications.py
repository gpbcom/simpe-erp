from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import List, Optional

# First-party imports
from models.enums import NotificationKind
from models.notifications.notification import Notification
from service.notifications.exceptions import MTNotificationNotFound
from storage.repositories.notification import NotificationRepository
from storage.repositories.user import UserRepository


class NotificationService:
    """Tells the right people that something needs their attention.

    Attributes:
        notifications (NotificationRepository): The notification store.
        users (UserRepository): The account store, used to resolve recipients.
        logger (Logger): Logger for notification operations.

    Notes:
        - Recipients are resolved **here**, from roles, rather than named by the
          caller. The thing publishing an event knows that a quote was
          submitted; it does not know who in the agency is allowed to rule on
          it, and it should not have to. A caller that named its own recipients
          would be a way to send a notification to anybody.
        - Fan-out failures are never fatal to the event that caused them. A
          quote is submitted whether or not the notification lands; refusing the
          submission because nobody could be told would be a worse outcome than
          a manager finding it in the queue unprompted.
    """

    def __init__(
        self,
        notifications: NotificationRepository,
        users: UserRepository,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            notifications (NotificationRepository): The notification store.
            users (UserRepository): The account store.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.notifications = notifications
        self.users = users
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("NotificationService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _utc_now(self) -> datetime:
        """Return the current instant as timezone-aware UTC.

        Returns:
            datetime: The current instant in UTC.
        """
        return datetime.now(UTC)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def notify_supervisors(
        self,
        company_id: Optional[str],
        kind: NotificationKind,
        title: str,
        body: Optional[str] = None,
        quote_id: Optional[str] = None,
    ) -> List[Notification]:
        """Tell every manager and administrator of an agency.

        Args:
            company_id (Optional[str]): The agency whose supervisors to tell.
            kind (NotificationKind): What the notification is about.
            title (str): The one-line summary.
            body (Optional[str]): The detail.
            quote_id (Optional[str]): The quote it points at.

        Returns:
            List[Notification]: The notifications written, one per supervisor.

        Notes:
            An agency with no active supervisor is logged at ``ERROR`` and
            produces nothing. It is a real operational fault — work is piling up
            with nobody able to release it — and it deserves to be loud rather
            than to look like a quiet day.
        """
        supervisors = await self.users.list_supervisors(company_id)
        if not supervisors:
            self.logger.error(
                "Nobody to notify about %r: company %s has no active manager "
                "or administrator.",
                title,
                company_id,
            )
            return []
        now = self._utc_now()
        pending = [
            Notification(
                recipient_id=supervisor.id,
                kind=kind,
                title=title,
                body=body,
                quote_id=quote_id,
                created_at=now,
            )
            for supervisor in supervisors
            if supervisor.id is not None
        ]
        written = await self.notifications.create_many(pending)
        self.logger.info(
            "Notified %d supervisor(s) of company %s: %s.",
            len(written),
            company_id,
            title,
        )
        return written

    async def notify_account(
        self,
        recipient_id: str,
        kind: NotificationKind,
        title: str,
        body: Optional[str] = None,
        quote_id: Optional[str] = None,
    ) -> Optional[Notification]:
        """Tell one account.

        Args:
            recipient_id (str): The account to tell.
            kind (NotificationKind): What the notification is about.
            title (str): The one-line summary.
            body (Optional[str]): The detail.
            quote_id (Optional[str]): The quote it points at.

        Returns:
            Optional[Notification]: The notification written, or ``None`` when
            no recipient was given.

        Notes:
            Used for the return leg of the quote workflow — telling an assistant
            that the quote they submitted was approved or sent back. A quote
            whose author is unknown produces nothing rather than failing: it was
            written before authorship was recorded, and that is not the
            assistant's problem to be told about.
        """
        if not recipient_id:
            self.logger.warning("Cannot deliver %r: no recipient was named.", title)  # noqa: E501
            return None
        written = await self.notifications.create(
            Notification(
                recipient_id=recipient_id,
                kind=kind,
                title=title,
                body=body,
                quote_id=quote_id,
                created_at=self._utc_now(),
            )
        )
        self.logger.info("Notified %s: %s.", recipient_id, title)
        return written

    async def list_for(
        self,
        recipient_id: str,
        page: int = 1,
        size: Optional[int] = None,
        unread_only: bool = False,
    ) -> List[Notification]:
        """Return a page of one account's notifications.

        Args:
            recipient_id (str): The account reading their own queue.
            page (int): One-based page number.
            size (Optional[int]): Page size.
            unread_only (bool): Restrict to notifications not yet read.

        Returns:
            List[Notification]: The matching notifications, newest first.
        """
        return await self.notifications.list_for(
            recipient_id=recipient_id,
            page=page,
            size=size,
            unread_only=unread_only,
        )

    async def unread_count(self, recipient_id: str) -> int:
        """Return how many notifications an account has not read.

        Args:
            recipient_id (str): The account whose badge is being drawn.

        Returns:
            int: The number of unread notifications.
        """
        return await self.notifications.count_unread(recipient_id)

    async def mark_read(self, notification_id: str, recipient_id: str) -> Notification:  # noqa: E501
        """Mark one of the reader's own notifications as read.

        Args:
            notification_id (str): The notification to mark.
            recipient_id (str): The account claiming it.

        Returns:
            Notification: The updated notification.

        Raises:
            MTNotificationNotFound: If it does not exist, or is addressed to
                somebody else.
        """
        marked = await self.notifications.mark_read(notification_id, recipient_id)  # noqa: E501
        if marked is None:
            raise MTNotificationNotFound(
                f"No notification {notification_id!r} is addressed to you."
            )
        return marked

    async def mark_all_read(self, recipient_id: str) -> int:
        """Clear an account's unread queue.

        Args:
            recipient_id (str): The account clearing their queue.

        Returns:
            int: How many notifications were marked read.
        """
        return await self.notifications.mark_all_read(recipient_id)
