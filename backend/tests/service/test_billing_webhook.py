from __future__ import annotations

# Standard library imports
from typing import Any, Dict, List

# Third-party imports
import httpx
import pytest

# First-party imports
from models.configuration.billing_webhook_config import BillingWebhookConfig
from service.billing.webhook import BillingWebhook

TOKEN_ENV = "BILLING_WEBHOOK_TOKEN_TEST"


class _Recorder:
    """Stands in for ``httpx.AsyncClient`` and records what was posted."""

    calls: List[Dict[str, Any]] = []
    failure: bool = False
    status_code: int = 200

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Accept whatever the client is constructed with.

        Args:
            *args (Any): Ignored.
            **kwargs (Any): Ignored.
        """

    async def __aenter__(self) -> "_Recorder":
        """Enter the context.

        Returns:
            _Recorder: This recorder.
        """
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Leave the context.

        Args:
            *args (Any): The exception triple, ignored.
        """

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Record a call and answer with the configured status.

        Args:
            url (str): Where the call went.
            **kwargs (Any): The payload and headers.

        Returns:
            httpx.Response: The canned answer.

        Raises:
            httpx.ConnectError: When the recorder is set to fail.
        """
        type(self).calls.append({"url": url, **kwargs})
        if type(self).failure:
            raise httpx.ConnectError("unreachable")
        return httpx.Response(
            type(self).status_code, request=httpx.Request("POST", url)
        )


@pytest.fixture(autouse=True)
def recorder(monkeypatch: pytest.MonkeyPatch) -> type[_Recorder]:
    """Replace the HTTP client and reset what it recorded.

    Args:
        monkeypatch (pytest.MonkeyPatch): Patches the client.

    Returns:
        type[_Recorder]: The recorder class, for assertions.
    """
    _Recorder.calls = []
    _Recorder.failure = False
    _Recorder.status_code = 200
    monkeypatch.setattr(httpx, "AsyncClient", _Recorder)
    return _Recorder


def a_webhook(enabled: bool = True) -> BillingWebhook:
    """Build a webhook pointed at a recorder.

    Args:
        enabled (bool): Whether the webhook is switched on.

    Returns:
        BillingWebhook: The announcer under test.
    """
    return BillingWebhook(
        BillingWebhookConfig(
            enabled=enabled,
            url="http://backend:8000/api/v1/webhooks/bill-accepted",
            token_env=TOKEN_ENV,
        )
    )


class TestTheAnnouncement:
    """Tests for what puts a validated invoice in a customer's inbox."""

    @pytest.mark.asyncio
    async def test_an_approved_invoice_is_announced(
        self, monkeypatch: pytest.MonkeyPatch, recorder: type[_Recorder]
    ) -> None:
        """**The only thing that sends an invoice.**

        Args:
            monkeypatch (pytest.MonkeyPatch): Sets the shared secret.
            recorder (type[_Recorder]): Records the call.

        Notes:
            Without this call the endpoint exists and nothing ever reaches it,
            and the failure is silent in both directions.
        """
        monkeypatch.setenv(TOKEN_ENV, "s3cret")

        assert await a_webhook().announce("bill-1") is True
        assert recorder.calls[0]["json"] == {"bill_id": "bill-1"}
        assert recorder.calls[0]["headers"]["X-Webhook-Token"] == "s3cret"

    @pytest.mark.asyncio
    async def test_the_payload_carries_an_identifier_and_nothing_else(
        self, monkeypatch: pytest.MonkeyPatch, recorder: type[_Recorder]
    ) -> None:
        """The endpoint re-reads the invoice rather than trusting the wire.

        Args:
            monkeypatch (pytest.MonkeyPatch): Sets the shared secret.
            recorder (type[_Recorder]): Records the call.

        Notes:
            Amounts travelling here would be a second copy of the document —
            one that could disagree with the stored one and decide what a
            customer is charged.
        """
        monkeypatch.setenv(TOKEN_ENV, "s3cret")
        await a_webhook().announce("bill-1")

        assert list(recorder.calls[0]["json"]) == ["bill_id"]

    @pytest.mark.asyncio
    async def test_a_disabled_webhook_stays_quiet(
        self, recorder: type[_Recorder]
    ) -> None:
        """Off is a decision, and makes no call at all.

        Args:
            recorder (type[_Recorder]): Records the call.
        """
        assert await a_webhook(enabled=False).announce("bill-1") is False
        assert recorder.calls == []

    @pytest.mark.asyncio
    async def test_an_unset_secret_refuses_and_says_which_variable(
        self, monkeypatch: pytest.MonkeyPatch, recorder: type[_Recorder]
    ) -> None:
        """Switched on and never configured is a misconfiguration, not a choice.

        Args:
            monkeypatch (pytest.MonkeyPatch): Clears the shared secret.
            recorder (type[_Recorder]): Records the call.

        Notes:
            Reported at warning naming the variable, because the symptom is
            invoices that are approved and never arrive.
        """
        monkeypatch.delenv(TOKEN_ENV, raising=False)

        assert await a_webhook().announce("bill-1") is False
        assert recorder.calls == []

    @pytest.mark.asyncio
    async def test_an_unreachable_dispatcher_never_raises(
        self, monkeypatch: pytest.MonkeyPatch, recorder: type[_Recorder]
    ) -> None:
        """**Logged and swallowed.**

        Args:
            monkeypatch (pytest.MonkeyPatch): Sets the shared secret.
            recorder (type[_Recorder]): Fails the call.

        Notes:
            The invoice is already written, numbered and downloadable. An
            unreachable mailer must not dead-letter the message; the bill stays
            at accepted, which reads as "approved but not yet out".
        """
        monkeypatch.setenv(TOKEN_ENV, "s3cret")
        recorder.failure = True

        assert await a_webhook().announce("bill-1") is False

    @pytest.mark.asyncio
    async def test_a_refused_call_is_reported_not_raised(
        self, monkeypatch: pytest.MonkeyPatch, recorder: type[_Recorder]
    ) -> None:
        """A dispatcher answering 401 is the same class of problem.

        Args:
            monkeypatch (pytest.MonkeyPatch): Sets the shared secret.
            recorder (type[_Recorder]): Answers with a refusal.
        """
        monkeypatch.setenv(TOKEN_ENV, "wrong")
        recorder.status_code = 401

        assert await a_webhook().announce("bill-1") is False

    def test_it_points_at_its_own_endpoint(self) -> None:
        """Never the planning one, and never with the planning secret."""
        config = BillingWebhookConfig()

        assert config.url.endswith("/api/v1/webhooks/bill-accepted")
        assert config.token_env == "BILLING_WEBHOOK_TOKEN"
