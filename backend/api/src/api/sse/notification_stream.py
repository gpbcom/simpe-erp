from __future__ import annotations

# Standard library imports
import asyncio
import json
from logging import Logger, getLogger
from typing import AsyncIterator, ClassVar, Dict, Optional

# Third-party imports
from fastapi import Request
from fastapi.responses import StreamingResponse

# First-party imports
from api.sse.broadcaster import NotificationBroadcaster
from models.notifications.notification import Notification


class NotificationStream:
    """Serves one account's notifications as a Server-Sent Events response.

    Attributes:
        KEEPALIVE_SECONDS (ClassVar[float]): How long the stream waits for a
            frame before writing a keep-alive comment.
        READY_FRAME (ClassVar[str]): The frame announcing the stream is live.
        KEEPALIVE_FRAME (ClassVar[str]): The comment frame written when idle.
        HEADERS (ClassVar[Dict[str, str]]): The headers every stream carries.
        request (Request): The incoming request, watched for disconnection.
        broadcaster (NotificationBroadcaster): The in-process fan-out.
        recipient_id (str): The account whose notifications are streamed.
        user_email (str): The account's address, for the log lines.
        logger (Logger): Logger for stream operations.

    Notes:
        - This exists as a class rather than a generator defined inside the
          route so that the framing rules — what a ready frame looks like, how
          long an idle stream waits, which headers a stream must carry — live
          somewhere they can be read and tested on their own, instead of inside
          a closure over a request.
        - A keep-alive comment goes out every ``KEEPALIVE_SECONDS`` so that an
          idle stream is not closed by a proxy. Proxies and load balancers close
          an idle connection, usually at sixty seconds, and a stream that is
          quiet all afternoon is the normal case. A comment frame is ignored by
          ``EventSource`` and costs three bytes.
        - The queue is unsubscribed in a ``finally``, so a client that vanishes
          mid-frame still releases its slot. Without it the broadcaster would
          accumulate one dead queue per connection that was ever opened.
    """

    KEEPALIVE_SECONDS: ClassVar[float] = 20.0
    READY_FRAME: ClassVar[str] = "event: ready\ndata: {}\n\n"
    KEEPALIVE_FRAME: ClassVar[str] = ": keep-alive\n\n"
    HEADERS: ClassVar[Dict[str, str]] = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        # Nginx buffers a response by default, which would hold every frame
        # until the stream closed — turning a live feed into one long silence
        # followed by a burst.
        "X-Accel-Buffering": "no",
    }

    def __init__(
        self,
        request: Request,
        broadcaster: NotificationBroadcaster,
        recipient_id: str,
        user_email: str,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the stream.

        Args:
            request (Request): The incoming request, watched for disconnection.
            broadcaster (NotificationBroadcaster): The in-process fan-out.
            recipient_id (str): The account whose notifications to stream.
            user_email (str): The account's address, for the log lines.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.request = request
        self.broadcaster = broadcaster
        self.recipient_id = recipient_id
        self.user_email = user_email
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("NotificationStream created for %s.", user_email)

    ############################
    # Internal Helpers Methods #
    ############################

    def _frame_for(self, notification: Notification) -> str:
        """Render one notification as an SSE frame.

        Args:
            notification (Notification): The notification to render.

        Returns:
            str: The frame to write.
        """
        payload = json.dumps(notification.model_dump(mode="json"))
        return f"event: notification\ndata: {payload}\n\n"

    ############################
    # Publicly Exposed Methods #
    ############################

    async def frames(self) -> AsyncIterator[str]:
        """Yield SSE frames until the client goes away.

        Yields:
            str: One SSE frame, either a notification or a keep-alive comment.

        Notes:
            The ready frame is announced immediately so a client knows the
            stream is live rather than merely accepted; a browser cannot
            otherwise tell the two apart until the first real event, which may
            be hours away.
        """
        queue = self.broadcaster.subscribe(self.recipient_id)
        try:
            yield self.READY_FRAME
            while True:
                if await self.request.is_disconnected():
                    self.logger.debug(
                        "The client behind the stream for %s disconnected.",
                        self.user_email,
                    )
                    break
                try:
                    notification = await asyncio.wait_for(
                        queue.get(), timeout=self.KEEPALIVE_SECONDS
                    )
                except TimeoutError:
                    yield self.KEEPALIVE_FRAME
                    continue
                yield self._frame_for(notification)
        except asyncio.CancelledError:
            # The server is shutting the connection down rather than the client
            # closing it. Nothing is wrong, but it is worth telling apart from a
            # clean client disconnect when a stream ends unexpectedly.
            self.logger.warning(
                "The stream for %s was cancelled before the client closed it.",
                self.user_email,
            )
            raise
        except Exception as exc:  # noqa: BLE001 - the connection is already open
            # There is no status left to change: the 200 and its headers went
            # out with the first frame. All that can be done is close the stream
            # and record why, rather than let it die silently mid-feed.
            self.logger.error(
                "The stream for %s failed and was closed: %s",
                self.user_email,
                exc,
            )
            raise
        finally:
            self.broadcaster.unsubscribe(self.recipient_id, queue)
            self.logger.info("Closed the event stream for %s.", self.user_email)

    def response(self) -> StreamingResponse:
        """Return the streaming response to hand back from a route.

        Returns:
            StreamingResponse: A ``text/event-stream`` response over
            :meth:`frames`.
        """
        self.logger.info("Opening an event stream for %s.", self.user_email)
        return StreamingResponse(
            self.frames(),
            media_type="text/event-stream",
            headers=dict(self.HEADERS),
        )
