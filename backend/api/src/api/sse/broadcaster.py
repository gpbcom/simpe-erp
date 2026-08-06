from __future__ import annotations

# Standard library imports
import asyncio
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Set

# First-party imports
from models.notifications.notification import Notification


class NotificationBroadcaster:
    """Hands a notification to whichever event streams are watching for it.

    Attributes:
        QUEUE_SIZE (ClassVar[int]): How many frames a slow reader may fall
            behind before the oldest are dropped.
        subscribers (Dict[str, Set[asyncio.Queue]]): The live queues, keyed by
            the account they belong to.
        logger (Logger): Logger for stream operations.

    Notes:
        - This is an **in-process** fan-out, and deliberately so. The streams
          are held open by this process; another process cannot write to them,
          so there is nothing to be gained by making the fan-out itself
          distributed. What crosses processes is the broker message, and each
          API instance publishes locally to the readers it happens to hold.
        - **Losing a frame is survivable; losing a notification is not.** The
          row is written to the database before anything is pushed, so a reader
          whose stream dropped finds the notification waiting on their next
          poll or reconnect. That is what lets this class stay simple: it is an
          accelerator, not a delivery guarantee.
        - A queue that fills is drained of its oldest frame rather than blocking
          the publisher. One reader on a bad connection must not be able to hold
          up every other reader, and the frame it loses is one it can still
          recover from the database.
    """

    QUEUE_SIZE: ClassVar[int] = 64

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the broadcaster.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.subscribers: Dict[str, Set[asyncio.Queue[Notification]]] = {}
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("NotificationBroadcaster created.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def subscribe(self, recipient_id: str) -> asyncio.Queue[Notification]:
        """Register a new stream for an account.

        Args:
            recipient_id (str): The account opening a stream.

        Returns:
            asyncio.Queue[Notification]: The queue that stream should read.

        Notes:
            One account may hold several streams at once — two browser tabs, a
            phone and a desktop — so the subscribers are a set per account
            rather than a single queue. Every one of them gets every frame.
        """
        queue: asyncio.Queue[Notification] = asyncio.Queue(maxsize=self.QUEUE_SIZE)  # noqa: E501
        self.subscribers.setdefault(recipient_id, set()).add(queue)
        self.logger.info(
            "Account %s opened an event stream (%d open).",
            recipient_id,
            len(self.subscribers[recipient_id]),
        )
        return queue

    def unsubscribe(
        self, recipient_id: str, queue: asyncio.Queue[Notification]
    ) -> None:
        """Drop a stream that has closed.

        Args:
            recipient_id (str): The account the stream belonged to.
            queue (asyncio.Queue[Notification]): The queue to forget.

        Notes:
            The account's entry is removed once its last stream goes, so the
            mapping does not grow by one dead key per account that has ever
            connected.
        """
        queues = self.subscribers.get(recipient_id)
        if queues is None:
            return
        queues.discard(queue)
        if not queues:
            self.subscribers.pop(recipient_id, None)
        self.logger.info("Account %s closed an event stream.", recipient_id)

    def publish(self, notification: Notification) -> int:
        """Push a notification to every stream its recipient holds.

        Args:
            notification (Notification): The notification to push.

        Returns:
            int: How many streams it reached. Zero is normal — it means the
            recipient is not currently connected.

        Notes:
            Never raises, and never blocks. A stream that has fallen behind
            loses its oldest frame instead of stalling the caller, because the
            caller is a broker consumer serving every other reader too.
        """
        queues = self.subscribers.get(notification.recipient_id)
        if not queues:
            self.logger.debug(
                "Account %s holds no open stream; the notification waits in "
                "the database.",
                notification.recipient_id,
            )
            return 0
        delivered = 0
        for queue in list(queues):
            if queue.full():
                # Drop the oldest rather than the newest: a reader catching up
                # wants the current state, and everything dropped is still in
                # the database behind them.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                self.logger.warning(
                    "A stream for %s is not keeping up; dropped a frame.",
                    notification.recipient_id,
                )
            try:
                queue.put_nowait(notification)
                delivered += 1
            except asyncio.QueueFull:
                self.logger.error(
                    "Could not push to a stream for %s even after draining it.",
                    notification.recipient_id,
                )
        self.logger.debug(
            "Pushed a notification to %d stream(s) for %s.",
            delivered,
            notification.recipient_id,
        )
        return delivered
