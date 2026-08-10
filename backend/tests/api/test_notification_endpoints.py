from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import get_current_user, get_notification_repository
from api.exception_handlers import ExceptionHandlers
from api.v1.notifications.notifications import (
    router as notifications_router,
    stream_notifications,
)
from models.auth.user import User
from models.enums import NotificationKind, UserRole
from models.notifications.notification import Notification
from service.auth.exceptions import MTAuthInvalidToken

READER = User(
    id="reader-1",
    company_id="company-1",
    email="claire.bernard@example.com",
    full_name="Claire Bernard",
    role=UserRole.MANAGER,
)


def a_notification(identifier: str, is_read: bool = False) -> Notification:
    """Return a notification addressed to the reader.

    Args:
        identifier (str): The notification's identifier.
        is_read (bool): Whether it has been read.

    Returns:
        Notification: The notification.
    """
    return Notification(
        id=identifier,
        recipient_id=READER.id,
        kind=NotificationKind.QUOTE_SUBMITTED,
        title=f"Devis {identifier} à valider",
        quote_id="quote-1",
        is_read=is_read,
        created_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
    )


@pytest.fixture
def notifications() -> MagicMock:
    """Return a stubbed notification store.

    Returns:
        MagicMock: A store answering with one unread notification.

    Notes:
        Overridden through ``dependency_overrides`` rather than pointed at a
        database: an unmocked repository would open a real connection, and
        these tests are about what the endpoints do with what it returns.
    """
    store = MagicMock()
    store.list_for = AsyncMock(return_value=[a_notification("n-1")])
    store.count_unread = AsyncMock(return_value=3)
    store.mark_read = AsyncMock(return_value=a_notification("n-1", is_read=True))
    store.mark_all_read = AsyncMock(return_value=3)
    return store


@pytest.fixture
def client(notifications: MagicMock) -> TestClient:
    """Return a client over the notification router alone.

    Args:
        notifications (MagicMock): The stubbed store.

    Returns:
        TestClient: A client authenticated as the reader.

    Notes:
        ``get_current_user`` is overridden rather than the authentication
        middleware being mounted. The middleware is tested on its own; what
        matters here is that every endpoint takes its recipient from the
        credential and from nowhere else.
    """
    app = FastAPI()
    app.include_router(notifications_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_notification_repository] = lambda: notifications
    app.dependency_overrides[get_current_user] = lambda: READER
    return TestClient(app, raise_server_exceptions=False)


class TestReading:
    """Tests for the endpoints a reader's inbox is drawn from."""

    def test_the_list_is_scoped_to_the_caller(
        self, client: TestClient, notifications: MagicMock
    ) -> None:
        """**The recipient is the credential.**

        Notes:
            There is no parameter that names a recipient, and the one passed to
            the store is taken from the authenticated caller. That is the whole
            of the access control on this route.
        """
        response = client.get("/api/v1/notifications")

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == ["n-1"]
        assert notifications.list_for.await_args.kwargs["recipient_id"] == "reader-1"

    def test_the_page_parameters_are_passed_through(
        self, client: TestClient, notifications: MagicMock
    ) -> None:
        """The popover asks for a page; the page is what it gets.

        Notes:
            An empty ``NotificationFilter`` always travels with the request:
            FastAPI binds one from the query string whether or not anything was
            filtered on. It narrows nothing, which is what the store's
            ``is_empty`` check is for.
        """
        client.get("/api/v1/notifications?page=2&size=10&unread_only=true")

        passed = notifications.list_for.await_args.kwargs
        assert passed["recipient_id"] == "reader-1"
        assert passed["page"] == 2
        assert passed["size"] == 10
        assert passed["unread_only"] is True
        assert passed["notification_filter"].is_empty() is True

    @pytest.mark.parametrize("query", ["page=0", "size=0", "size=201"])
    def test_an_impossible_page_is_refused(
        self, client: TestClient, query: str
    ) -> None:
        """A page size of two hundred and one is a way to ask for everything."""
        assert client.get(f"/api/v1/notifications?{query}").status_code == 422

    def test_the_badge_is_served_without_a_page_of_notifications(
        self, client: TestClient, notifications: MagicMock
    ) -> None:
        """Counted rather than fetched-and-measured."""
        response = client.get("/api/v1/notifications/unread-count")

        assert response.status_code == 200
        assert response.json() == {"unread": 3}
        notifications.count_unread.assert_awaited_once_with("reader-1")
        notifications.list_for.assert_not_awaited()


class TestMarkingRead:
    """Tests for clearing a reader's queue."""

    def test_marking_one_read_returns_it(
        self, client: TestClient, notifications: MagicMock
    ) -> None:
        """The client patches its row from the answer rather than refetching."""
        response = client.post("/api/v1/notifications/n-1/read")

        assert response.status_code == 200
        assert response.json()["is_read"] is True
        notifications.mark_read.assert_awaited_once_with("n-1", "reader-1")

    def test_another_account_s_notification_answers_404(
        self, client: TestClient, notifications: MagicMock
    ) -> None:
        """**The same 404 as one that does not exist, deliberately.**

        Notes:
            Telling the two apart would confirm the existence of other people's
            notifications to anybody willing to guess identifiers.
        """
        notifications.mark_read = AsyncMock(return_value=None)

        response = client.post("/api/v1/notifications/somebody-elses/read")

        assert response.status_code == 404
        assert "somebody-elses" in response.json()["detail"]

    def test_an_unknown_notification_answers_404(
        self, client: TestClient, notifications: MagicMock
    ) -> None:
        """Indistinguishable from the case above, which is the point."""
        notifications.mark_read = AsyncMock(return_value=None)

        assert client.post("/api/v1/notifications/no-such-id/read").status_code == 404

    def test_clearing_the_queue_reports_how_many_were_marked(
        self, client: TestClient, notifications: MagicMock
    ) -> None:
        """The button that draws the badge back to zero."""
        response = client.post("/api/v1/notifications/read-all")

        assert response.status_code == 200
        assert response.json() == {"marked": 3}
        notifications.mark_all_read.assert_awaited_once_with("reader-1")


class TestPersistenceAcrossSessions:
    """Tests for a reader finding their notifications after signing back in."""

    def test_signing_back_in_still_shows_the_unread_queue(
        self, client: TestClient, notifications: MagicMock
    ) -> None:
        """**Nothing about a notification is tied to a login.**

        Notes:
            A new sign-in is a new credential over the same rows: the endpoints
            resolve the recipient from the token and read the same table. There
            is no per-session state to lose, which is why the event stream is
            allowed to carry no data — a reader who was offline for the push
            finds everything here.
        """
        first = client.get("/api/v1/notifications/unread-count")

        # A second call standing in for the next sign-in: a different token, the
        # same account, and nothing in between that could have cleared anything.
        second = client.get("/api/v1/notifications/unread-count")
        listed = client.get("/api/v1/notifications")

        assert first.json() == second.json() == {"unread": 3}
        assert [item["id"] for item in listed.json()] == ["n-1"]
        assert notifications.mark_all_read.await_count == 0


class TestStream:
    """Tests for the event-stream endpoint's own authentication.

    Notes:
        Driven by calling the route directly rather than through a client. The
        endpoint returns a response that stays open until the client goes away,
        and a test client never goes away — reading it would block until the
        test timed out. What is worth asserting here is the handover: the token
        is verified, and the stream is opened for the account it named. The
        frames themselves are covered in ``test_notification_streams.py``.
    """

    async def test_the_token_is_verified_before_a_stream_is_opened(self) -> None:
        """A stream is a subscription to somebody's notifications."""
        auth = MagicMock()
        auth.resolve_stream_token = AsyncMock(return_value=READER)
        streams = MagicMock()

        await stream_notifications(
            request=MagicMock(spec=Request),
            token="short-lived",
            auth=auth,
            streams=streams,
        )

        auth.resolve_stream_token.assert_awaited_once_with("short-lived")

    async def test_the_stream_is_opened_for_the_account_the_token_named(self) -> None:
        """**Not for an account named in the request.**

        Notes:
            The recipient comes from the verified token, so a caller cannot open
            somebody else's stream by asking for it — there is no parameter with
            which to ask.
        """
        auth = MagicMock()
        auth.resolve_stream_token = AsyncMock(return_value=READER)
        streams = MagicMock()

        await stream_notifications(
            request=MagicMock(spec=Request),
            token="short-lived",
            auth=auth,
            streams=streams,
        )

        assert streams.response.call_args.kwargs["recipient_id"] == "reader-1"

    async def test_an_invalid_token_opens_nothing(self) -> None:
        """The 401 comes from the auth service; no stream is registered."""
        auth = MagicMock()
        auth.resolve_stream_token = AsyncMock(side_effect=MTAuthInvalidToken("expired"))
        streams = MagicMock()

        with pytest.raises(MTAuthInvalidToken):
            await stream_notifications(
                request=MagicMock(spec=Request),
                token="expired",
                auth=auth,
                streams=streams,
            )

        streams.response.assert_not_called()
