from __future__ import annotations

# Standard library imports
from typing import List, Optional, Tuple

# Third-party imports
import httpx
import pytest

# First-party imports
from models.configuration.webhook_config import WebhookConfig
from service.planning.webhook import PlanningWebhook
from tests.annotations import ModelInput


def _config(
    enabled: bool = True, token_env: str = "TEST_WEBHOOK_TOKEN"
) -> WebhookConfig:
    """Build a webhook configuration.

    Args:
        enabled (bool): Whether announcing is switched on.
        token_env (str): The variable the shared secret is read from.

    Returns:
        WebhookConfig: The configuration.
    """
    return WebhookConfig(
        enabled=enabled,
        url="http://backend:8000/api/v1/webhooks/planning-completed",
        token_env=token_env,
        timeout_seconds=5.0,
    )


class _Transport(httpx.AsyncBaseTransport):
    """A transport that records what was sent and answers a fixed status.

    Attributes:
        status (int): The status every request is answered with.
        calls (List[Tuple[str, Optional[str], bytes]]): One entry per request:
            the URL, the ``X-Webhook-Token`` header and the body.
        failure (Optional[Exception]): Raised instead of answering, when set.

    Notes:
        A transport rather than a patched ``httpx.AsyncClient``. The thing
        worth pinning is what leaves the process — the URL, the secret header
        and the payload — and a stub swapped in at the client level asserts
        only that some method was called.
    """

    def __init__(self, status: int = 200, failure: Optional[Exception] = None) -> None:
        """Initialize the transport.

        Args:
            status (int): The status to answer with.
            failure (Optional[Exception]): Raised instead of answering.
        """
        self.status = status
        self.failure = failure
        self.calls: List[Tuple[str, Optional[str], bytes]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Record the request and answer it.

        Args:
            request (httpx.Request): The outgoing request.

        Returns:
            httpx.Response: The canned answer.

        Raises:
            Exception: The configured failure, when there is one.
        """
        self.calls.append(
            (str(request.url), request.headers.get("X-Webhook-Token"), request.content)
        )
        if self.failure is not None:
            raise self.failure
        return httpx.Response(self.status, json={"ok": True})


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> _Transport:
    """Return a recording transport, wired into every client the code builds.

    Args:
        monkeypatch (pytest.MonkeyPatch): Patching helper.

    Returns:
        _Transport: The transport, holding what was sent.
    """
    recorder = _Transport()
    original = httpx.AsyncClient.__init__

    def _with_transport(self: httpx.AsyncClient, **kwargs: ModelInput) -> None:
        """Build the client on the recording transport.

        Args:
            self (httpx.AsyncClient): The client being built.
            **kwargs (ModelInput): Whatever the caller passed.
        """
        original(self, transport=recorder, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _with_transport)
    return recorder


class TestAnnouncingASucceededRun:
    """Tests the call that turns a finished planning into documents."""

    @pytest.mark.asyncio
    async def test_it_posts_the_run_to_the_configured_url(
        self, transport: _Transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The dispatcher is told which run to send."""
        monkeypatch.setenv("TEST_WEBHOOK_TOKEN", "s3cret")

        assert await PlanningWebhook(config=_config()).announce("run-1") is True

        url, _, body = transport.calls[0]
        assert url.endswith("/api/v1/webhooks/planning-completed")
        assert b"run-1" in body

    @pytest.mark.asyncio
    async def test_it_carries_the_shared_secret(
        self, transport: _Transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The endpoint has no signed-in user; the header is what authenticates."""
        monkeypatch.setenv("TEST_WEBHOOK_TOKEN", "s3cret")

        await PlanningWebhook(config=_config()).announce("run-1")

        assert transport.calls[0][1] == "s3cret"

    @pytest.mark.asyncio
    async def test_a_disabled_webhook_sends_nothing(
        self, transport: _Transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Emailing the whole workforce is opt-in."""
        monkeypatch.setenv("TEST_WEBHOOK_TOKEN", "s3cret")

        result = await PlanningWebhook(config=_config(enabled=False)).announce("run-1")

        assert result is False
        assert transport.calls == []

    @pytest.mark.asyncio
    async def test_an_unset_secret_sends_nothing(
        self, transport: _Transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**The half-configured case**, which is the likely one.

        Notes:
            Somebody switches the webhook on and stops there. Calling anyway
            would post an unauthenticated request that the endpoint answers 401
            — a mail dispatch that fails for a reason nothing on either side
            explains.
        """
        monkeypatch.delenv("TEST_WEBHOOK_TOKEN", raising=False)

        assert await PlanningWebhook(config=_config()).announce("run-1") is False
        assert transport.calls == []

    @pytest.mark.asyncio
    async def test_a_refused_call_is_swallowed(
        self, transport: _Transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A good run must not be turned into a failed one by a mailer."""
        monkeypatch.setenv("TEST_WEBHOOK_TOKEN", "s3cret")
        transport.status = 500

        assert await PlanningWebhook(config=_config()).announce("run-1") is False

    @pytest.mark.asyncio
    async def test_an_unreachable_dispatcher_is_swallowed(
        self, transport: _Transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The planning is already stored; the documents can be resent by hand."""
        monkeypatch.setenv("TEST_WEBHOOK_TOKEN", "s3cret")
        transport.failure = httpx.ConnectError("no route to host")

        assert await PlanningWebhook(config=_config()).announce("run-1") is False
