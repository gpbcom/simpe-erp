from __future__ import annotations

# Standard library imports
import asyncio
from logging import Logger, getLogger
from typing import AsyncIterator, ClassVar, Dict, Optional, Set

# Third-party imports
from fastapi import Request
from fastapi.responses import StreamingResponse

# First-party imports
from models.messaging.event_envelope import EventEnvelope


class NotificationStreams:
    """The event streams this API instance is holding open, and what wakes them.

    Attributes:
        QUEUE_SIZE (ClassVar[int]): How many wake-ups a stream may have
            pending. One: they are indistinguishable, so a second would only
            produce a duplicate refetch.
        KEEPALIVE_SECONDS (ClassVar[float]): How long a stream waits for a
            wake-up before writing a keep-alive comment.
        READY_FRAME (ClassVar[str]): The frame announcing the stream is live.
        NOTIFICATION_FRAME (ClassVar[str]): The frame telling a reader that
            something changed.
        KEEPALIVE_FRAME (ClassVar[str]): The comment frame written when idle.
        HEADERS (ClassVar[Dict[str, str]]): The headers every stream carries.
        subscribers (Dict[str, Set[asyncio.Queue]]): The live queues, keyed by
            the account they belong to.
        logger (Logger): Logger for stream operations.

    Notes:
        - **A frame carries no data, only the news that there is some.** The
          reader fetches the notifications themselves over HTTP, from the same
          endpoint it would have used had the push never arrived. That keeps
          one source of truth instead of two that can disagree, means a
          notification is never delivered by a route that cannot also replay it
          after a logout, and lets a message on the broker carry identifiers
          rather than records.
        - **Losing a frame is survivable; losing a notification is not.** The
          row is written to the database before anything is pushed, so a reader
          whose stream dropped finds the notification waiting when it
          reconnects — the ``ready`` frame tells it to look. That is what lets
          this class stay simple: it is an accelerator, not a delivery
          guarantee.
        - The fan-out is **in-process**, and deliberately so. The streams are
          held open by this process; another process cannot write to them. What
          crosses processes is the broker message, which every API instance
          receives on a queue of its own and turns into wake-ups for the
          readers it happens to hold.
        - Waking never blocks and never queues behind itself. A reader that
          already has a wake-up pending is left alone: the frames are identical
          and carry nothing, so one produces the same refetch as ten. One
          reader on a bad connection therefore cannot hold up the relay serving
          every other reader.
        - The registry and the framing live in **one** class rather than a
          broadcaster and a stream. There is one thing here — the set of
          readers this instance is serving — and splitting it meant a per-request
          object reaching into a process-wide one on every frame.
    """

    QUEUE_SIZE: ClassVar[int] = 1
    KEEPALIVE_SECONDS: ClassVar[float] = 20.0
    READY_FRAME: ClassVar[str] = "event: ready\ndata: {}\n\n"
    NOTIFICATION_FRAME: ClassVar[str] = "event: notification\ndata: {}\n\n"
    KEEPALIVE_FRAME: ClassVar[str] = ": keep-alive\n\n"
    HEADERS: ClassVar[Dict[str, str]] = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the registry.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.subscribers: Dict[str, Set[asyncio.Queue[None]]] = {}
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("NotificationStreams created.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _subscribe(self, recipient_id: str) -> asyncio.Queue[None]:
        """Register a new stream for an account.

        Args:
            recipient_id (str): The account opening a stream.

        Returns:
            asyncio.Queue[None]: The queue that stream should read.

        Notes:
            One account may hold several streams at once — two browser tabs, a
            phone and a desktop — so the subscribers are a set per account
            rather than a single queue. Every one of them is woken.
        """
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=self.QUEUE_SIZE)
        self.subscribers.setdefault(recipient_id, set()).add(queue)
        self.logger.info(
            "Account %s opened an event stream (%d open).",
            recipient_id,
            len(self.subscribers[recipient_id]),
        )
        return queue

    def _unsubscribe(self, recipient_id: str, queue: asyncio.Queue[None]) -> None:  # noqa: E501
        """Drop a stream that has closed.

        Args:
            recipient_id (str): The account the stream belonged to.
            queue (asyncio.Queue[None]): The queue to forget.

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

    async def _frames(
        self, request: Request, recipient_id: str, user_email: str
    ) -> AsyncIterator[str]:
        """Yield SSE frames until the client goes away.

        Args:
            request (Request): The incoming request, watched for disconnection.
            recipient_id (str): The account being served.
            user_email (str): The account's address, for the log lines.

        Yields:
            str: One SSE frame: ready, a notification signal, or a keep-alive
            comment.

        Notes:
            - The ready frame is announced immediately so a client knows the
              stream is live rather than merely accepted; a browser cannot
              otherwise tell the two apart until the first real event, which may
              be hours away. It doubles as the catch-up signal: a client that
              refetches on ``ready`` recovers everything it missed while the
              stream was down, on every reconnect rather than on a timer.
            - A keep-alive comment goes out every ``KEEPALIVE_SECONDS`` so that
              an idle stream is not closed by a proxy. Proxies and load
              balancers close an idle connection, usually at sixty seconds, and
              a stream that is quiet all afternoon is the normal case. A comment
              frame is ignored by ``EventSource`` and costs three bytes.
            - The queue is unsubscribed in a ``finally``, so a client that
              vanishes mid-frame still releases its slot. Without it the
              registry would accumulate one dead queue per connection that was
              ever opened.
        """
        queue = self._subscribe(recipient_id)
        try:
            yield self.READY_FRAME
            while True:
                if await request.is_disconnected():
                    self.logger.debug(
                        "The client behind the stream for %s disconnected.",
                        user_email,
                    )
                    break
                try:
                    await asyncio.wait_for(queue.get(), timeout=self.KEEPALIVE_SECONDS)  # noqa: E501
                except TimeoutError:
                    yield self.KEEPALIVE_FRAME
                    continue
                yield self.NOTIFICATION_FRAME
        except asyncio.CancelledError:
            self.logger.warning(
                "The stream for %s was cancelled before the client closed it.",
                user_email,
            )
            raise
        except Exception as exc:  # noqa: BLE001 - the connection is already open
            self.logger.error(
                "The stream for %s failed and was closed: %s",
                user_email,
                exc,
            )
            raise
        finally:
            self._unsubscribe(recipient_id, queue)
            self.logger.info("Closed the event stream for %s.", user_email)

    ############################
    # Publicly Exposed Methods #
    ############################

    def wake(self, recipient_id: str) -> int:
        """Tell every stream an account holds that it has something to fetch.

        Args:
            recipient_id (str): The account to wake.

        Returns:
            int: How many streams were woken. Zero is normal — it means the
            account is not currently connected.

        Notes:
            - Never raises, and never blocks. The caller is a broker consumer
              serving every other reader too, so one reader must not be able to
              stall it.
            - A stream that already has a wake-up pending is skipped rather than
              queued behind. The wake-ups are indistinguishable and carry
              nothing, so a second would only make a reader that has just
              reconnected fire a duplicate request. The count returned is
              therefore streams *newly* woken, not streams that will refetch —
              the skipped ones were already going to.
        """
        queues = self.subscribers.get(recipient_id)
        if not queues:
            self.logger.debug(
                "Account %s holds no open stream; the notification waits in "
                "the database.",
                recipient_id,
            )
            return 0
        woken = 0
        for queue in list(queues):
            if queue.empty():
                queue.put_nowait(None)
                woken += 1
        self.logger.debug("Woke %d stream(s) for %s.", woken, recipient_id)
        return woken

    async def relay(self, envelope: EventEnvelope) -> None:
        """Turn a ``notification.created`` message into wake-ups.

        Args:
            envelope (EventEnvelope): The message, carrying ``recipient_ids``.

        Notes:
            **Never raises.** The rows this announces are already committed, so
            a malformed message costs a push, not a notification — and
            dead-lettering it would make a cosmetic fault look like a lost one.
            A recipient with no open stream on this instance is the common case,
            not an error: they are reading somewhere else, or not reading at
            all.
        """
        recipients = envelope.payload.get("recipient_ids")
        if not isinstance(recipients, list):
            self.logger.warning(
                "A %s message named no recipients; nothing to wake.",
                envelope.routing_key,
            )
            return
        woken = sum(
            self.wake(recipient)
            for recipient in recipients
            if isinstance(recipient, str) and recipient
        )
        self.logger.info(
            "Relayed %s to %d open stream(s).", envelope.routing_key, woken
        )

    def response(
        self, request: Request, recipient_id: str, user_email: str
    ) -> StreamingResponse:
        """Return the streaming response to hand back from a route.

        Args:
            request (Request): The incoming request, watched for disconnection.
            recipient_id (str): The account whose stream to open.
            user_email (str): The account's address, for the log lines.

        Returns:
            StreamingResponse: A ``text/event-stream`` response over
            :meth:`_frames`.
        """
        self.logger.info("Opening an event stream for %s.", user_email)
        return StreamingResponse(
            self._frames(request, recipient_id, user_email),
            media_type="text/event-stream",
            headers=dict(self.HEADERS),
        )
