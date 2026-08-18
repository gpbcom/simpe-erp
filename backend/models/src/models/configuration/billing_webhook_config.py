from __future__ import annotations

# Third-party imports
from pydantic import Field

# First-party imports
from models.configuration.webhook_config import WebhookConfig


class BillingWebhookConfig(WebhookConfig):
    """Settings for the webhook that emails a validated invoice.

    Attributes:
        enabled (bool): Whether validating a bill calls the webhook.
        url (str): The endpoint to call once a manager approves a bill.
        paid_url (str): The endpoint to call once a bill is marked paid.
        token_env (str): Name of the environment variable holding the shared
            secret sent as ``X-Webhook-Token`` and checked on the way in.
        timeout_seconds (float): How long to wait on the call.

    Notes:
        - **A subclass rather than a second field of the base type**, because
          :class:`~models.configuration.webhook_config.WebhookConfig`'s own
          defaults are planning-shaped. Mounted as a plain ``WebhookConfig``, a
          deployment whose YAML lacked a ``billing_webhook`` block would send an
          invoice announcement to the *planning* endpoint carrying the
          *planning* secret — a misconfiguration that authenticates
          successfully and does the wrong thing, which is the worst kind.
        - It inherits every validator and therefore needs no exception family of
          its own. A bad URL or timeout is refused exactly as the planning
          webhook's would be.
        - Disabled by default, like its parent. An agency that has not
          configured outbound mail should approve invoices without anything
          being attempted, rather than watching every validation log a failure.
    """

    url: str = Field(
        default="http://localhost:8000/api/v1/webhooks/bill-accepted",
        description="The endpoint called once a manager approves a bill.",
    )
    paid_url: str = Field(
        default="http://localhost:8000/api/v1/webhooks/bill-paid",
        description="The endpoint called once a bill is marked paid.",
    )
    token_env: str = Field(
        default="BILLING_WEBHOOK_TOKEN",
        description="Name of the env var holding the shared secret.",
    )
