from __future__ import annotations

# Standard library imports
from typing import AsyncIterator, Dict, List

# Third-party imports
import pytest

# First-party imports
from api.sse.streams import NotificationStreams
from models.messaging.event_envelope import EventEnvelope


class StubRequest:
    """A request that reports whether the client is still there.

    Attributes:
        disconnect_after (int): How many checks to answer "connected" before
            reporting the client has gone.
        checks (int): How many times the stream has asked.

    Notes:
        Stands in for a Starlette ``Request`` because the stream only ever asks
        it one question. Building a real one would need an ASGI scope, a
        receive channel and a running server for no gain.
    """

    def __init__(self, disconnect_after: int = 1) -> None:
        """Initialize the stub.

        Args:
            disconnect_after (int): Number of checks answered "connected".
        """
        self.disconnect_after = disconnect_after
        self.checks = 0

    async def is_disconnected(self) -> bool:
        """Report whether the client has gone.

        Returns:
            bool: ``True`` once the stream has asked often enough.
        """
        self.checks += 1
        return self.checks > self.disconnect_after


@pytest.fixture
def streams() -> NotificationStreams:
    """Return an empty registry.

    Returns:
        NotificationStreams: A registry holding no streams.
    """
    return NotificationStreams()


async def drain(frames: AsyncIterator[str]) -> List[str]:
    """Collect every frame a stream yields before it closes.

    Args:
        frames (AsyncIterator[str]): The stream's frames.

    Returns:
        List[str]: The frames, in order.
    """
    return [frame async for frame in frames]


class TestWaking:
    """Tests for turning a written notification into a wake-up."""

    def test_an_account_with_no_open_stream_is_not_an_error(
        self, streams: NotificationStreams
    ) -> None:
        """Nobody connected is the normal case, not a failure.

        Notes:
            The notification is already in the database; the reader will find it
            when they next look.
        """
        assert streams.wake("nobody") == 0

    def test_every_stream_an_account_holds_is_woken(
        self, streams: NotificationStreams
    ) -> None:
        """Two tabs, a phone and a desktop all get the news."""
        first = streams._subscribe("reader-1")
        second = streams._subscribe("reader-1")

        assert streams.wake("reader-1") == 2
        assert first.qsize() == 1
        assert second.qsize() == 1

    def test_a_second_wake_up_is_not_queued_behind_the_first(
        self, streams: NotificationStreams
    ) -> None:
        """**Why the queue holds one and not sixty-four.**

        Notes:
            The frames are indistinguishable and carry nothing, so a pending
            wake-up already says everything the second would. Queueing it would
            only make a reader that has just reconnected fire a burst of
            identical refetches.
        """
        queue = streams._subscribe("reader-1")

        assert streams.wake("reader-1") == 1
        assert streams.wake("reader-1") == 0
        assert queue.qsize() == 1

    def test_waking_one_account_does_not_wake_another(
        self, streams: NotificationStreams
    ) -> None:
        """A wake-up is addressed, not broadcast."""
        mine = streams._subscribe("reader-1")
        theirs = streams._subscribe("reader-2")

        streams.wake("reader-1")

        assert mine.qsize() == 1
        assert theirs.qsize() == 0

    def test_the_last_stream_to_close_takes_the_account_with_it(
        self, streams: NotificationStreams
    ) -> None:
        """Otherwise the registry grows by a dead key per account ever seen."""
        first = streams._subscribe("reader-1")
        second = streams._subscribe("reader-1")

        streams._unsubscribe("reader-1", first)
        assert "reader-1" in streams.subscribers

        streams._unsubscribe("reader-1", second)
        assert streams.subscribers == {}

    def test_unsubscribing_a_stream_twice_is_harmless(
        self, streams: NotificationStreams
    ) -> None:
        """The ``finally`` that calls it can run after the account is gone."""
        queue = streams._subscribe("reader-1")
        streams._unsubscribe("reader-1", queue)

        streams._unsubscribe("reader-1", queue)

        assert streams.subscribers == {}


class TestRelay:
    """Tests for the broker message that drives the wake-ups."""

    async def test_every_named_recipient_is_woken(
        self, streams: NotificationStreams
    ) -> None:
        """One message announces a whole fan-out."""
        mine = streams._subscribe("reader-1")
        theirs = streams._subscribe("reader-2")

        await streams.relay(
            EventEnvelope(
                routing_key="notification.created",
                payload={"recipient_ids": ["reader-1", "reader-2"]},
            )
        )

        assert mine.qsize() == 1
        assert theirs.qsize() == 1

    async def test_a_recipient_reading_elsewhere_is_skipped_quietly(
        self, streams: NotificationStreams
    ) -> None:
        """Each instance wakes only the readers it happens to hold."""
        mine = streams._subscribe("reader-1")

        await streams.relay(
            EventEnvelope(
                routing_key="notification.created",
                payload={"recipient_ids": ["reader-1", "reader-on-another-instance"]},
            )
        )

        assert mine.qsize() == 1

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"recipient_ids": None},
            {"recipient_ids": "reader-1"},
            {"recipient_ids": [42, "", None]},
        ],
    )
    async def test_a_malformed_message_never_raises(
        self, streams: NotificationStreams, payload: Dict[str, object]
    ) -> None:
        """**A cosmetic fault must not look like a lost notification.**

        Notes:
            The rows this announces are already committed. Raising would
            dead-letter the message, which is the handling reserved for work
            that did not happen — and this work did.
        """
        streams._subscribe("reader-1")

        await streams.relay(
            EventEnvelope(routing_key="notification.created", payload=payload)
        )

        assert streams.subscribers["reader-1"].pop().qsize() == 0


class TestFrames:
    """Tests for what goes down the wire."""

    async def test_a_stream_announces_itself_before_anything_else(
        self, streams: NotificationStreams
    ) -> None:
        """A browser cannot otherwise tell accepted from live.

        Notes:
            It doubles as the catch-up signal — a client refetches on it, which
            is what recovers everything written while the stream was down.
        """
        frames = await drain(
            streams._frames(
                StubRequest(disconnect_after=0), "reader-1", "r@example.com"
            )
        )

        assert frames == [NotificationStreams.READY_FRAME]

    async def test_an_idle_stream_writes_a_keep_alive(
        self, monkeypatch: pytest.MonkeyPatch, streams: NotificationStreams
    ) -> None:
        """A proxy closes a connection that has said nothing for a minute."""
        monkeypatch.setattr(NotificationStreams, "KEEPALIVE_SECONDS", 0.01)

        frames = await drain(
            streams._frames(
                StubRequest(disconnect_after=1), "reader-1", "r@example.com"
            )
        )

        assert frames == [
            NotificationStreams.READY_FRAME,
            NotificationStreams.KEEPALIVE_FRAME,
        ]

    async def test_a_wake_up_becomes_a_notification_frame(
        self, streams: NotificationStreams
    ) -> None:
        """The frame carries no data — only the news that there is some."""
        request = StubRequest(disconnect_after=1)
        frames = streams._frames(request, "reader-1", "r@example.com")

        assert await anext(frames) == NotificationStreams.READY_FRAME
        streams.wake("reader-1")

        assert await anext(frames) == NotificationStreams.NOTIFICATION_FRAME

        await frames.aclose()

    async def test_a_closed_stream_releases_its_slot(
        self, streams: NotificationStreams
    ) -> None:
        """Without it the registry leaks a queue per connection ever opened."""
        await drain(
            streams._frames(
                StubRequest(disconnect_after=0), "reader-1", "r@example.com"
            )
        )

        assert streams.subscribers == {}

    async def test_a_stream_abandoned_mid_frame_releases_its_slot(
        self, streams: NotificationStreams
    ) -> None:
        """A client that vanishes never reaches the disconnect check."""
        frames = streams._frames(StubRequest(disconnect_after=99), "r-1", "r@e.com")
        await anext(frames)
        assert streams.subscribers["r-1"]

        await frames.aclose()

        assert streams.subscribers == {}

    def test_the_response_refuses_to_be_buffered(
        self, streams: NotificationStreams
    ) -> None:
        """Nginx buffering turns a live feed into one long silence."""
        response = streams.response(StubRequest(), "reader-1", "r@example.com")

        assert response.media_type == "text/event-stream"
        assert response.headers["x-accel-buffering"] == "no"
        assert response.headers["cache-control"] == "no-cache"

    def test_the_frames_are_valid_server_sent_events(self) -> None:
        """``EventSource`` needs the blank line; a comment needs the colon.

        Notes:
            The event names are the contract with the browser: the client
            listens for ``ready`` and ``notification`` by name, and a frame
            renamed here goes unheard rather than failing.
        """
        assert NotificationStreams.READY_FRAME.startswith("event: ready")
        assert NotificationStreams.READY_FRAME.endswith("\n\n")
        assert NotificationStreams.NOTIFICATION_FRAME.startswith("event: notification")
        assert NotificationStreams.NOTIFICATION_FRAME.endswith("\n\n")
        assert NotificationStreams.KEEPALIVE_FRAME.startswith(":")
