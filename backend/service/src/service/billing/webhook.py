from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import Optional

# Third-party imports
import httpx

# First-party imports
from models.configuration.billing_webhook_config import BillingWebhookConfig


class BillingWebhook:
    """Announces a validated invoice to whatever emails it.

    Attributes:
        config (BillingWebhookConfig): Where to call, and with which shared
            secret.
        logger (Logger): Logger for announcements.

    Notes:
        - **This is the only thing that puts an invoice in a customer's inbox.**
          A generation run renders every document and stops; the manager's move
          to accepted is what fires this call, and without it the endpoint
          exists and nothing ever reaches it. The failure would be silent in
          both directions: no error logged, and no invoice sent.
        - **A class in ``service``, called from the worker.** The worker
          deliberately does not depend on ``api``, so the announcement cannot
          live in the API's dependency module — the same arrangement
          :class:`~service.planning.webhook.PlanningWebhook` has, and for the
          same reason.
        - A failure is **logged and swallowed**. The invoice is already written,
          numbered and downloadable; an unreachable mailer must not dead-letter
          the message, and the bill simply stays at accepted — which reads as
          "approved but not yet out", the truth, and is actionable.
    """

    def __init__(
        self,
        config: BillingWebhookConfig,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the announcer.

        Args:
            config (BillingWebhookConfig): Where to call, and with which secret.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug(
            "BillingWebhook created for %s (enabled=%s).",
            self.config.url,
            self.config.enabled,
        )

    ############################
    # Internal Helpers Methods #
    ############################

    async def _announce_to(self, url: str, bill_id: str, what: str) -> bool:
        """Post an invoice identifier to one of the billing webhooks.

        Args:
            url (str): The endpoint to call.
            bill_id (str): The invoice being announced.
            what (str): What happened to it, for the log lines.

        Returns:
            bool: ``True`` when the call was made and accepted.

        Notes:
            Shared by both announcements because the transport is identical and
            only the destination differs. Two copies would drift, and the half
            that drifted would be the one nobody exercises until an invoice is
            settled.
        """
        if not self.config.enabled:
            self.logger.debug(
                "The billing webhook is disabled; not announcing bill %s (%s).",
                bill_id,
                what,
            )
            return False
        token = self.config.get_token()
        if not token:
            self.logger.warning(
                "Not announcing bill %s (%s): the webhook secret (%s) is unset.",
                bill_id,
                what,
                self.config.token_env,
            )
            return False
        self.logger.info("Announcing bill %s (%s) to %s.", bill_id, what, url)
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:  # noqa: E501
                response = await client.post(
                    url,
                    json={"bill_id": bill_id},
                    headers={"X-Webhook-Token": token},
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            self.logger.error("Could not announce bill %s: %s", bill_id, exc)
            return False
        self.logger.info(
            "Bill %s announced; the dispatcher answered %d.",
            bill_id,
            response.status_code,
        )
        return True

    ############################
    # Publicly Exposed Methods #
    ############################

    async def announce_paid(self, bill_id: str) -> bool:
        """Tell the transmitter that an invoice has been collected.

        Args:
            bill_id (str): The invoice that was settled.

        Returns:
            bool: ``True`` when the call was made and accepted.

        Notes:
            - **A separate endpoint from the approval one, because it is a
              different obligation.** Approval emails a document to a customer;
              collection is what the tax authority wants declared, since VAT on
              services falls due when the money arrives rather than when the care
              was delivered.
            - Shares the approval webhook's secret on purpose: both are this
              application calling itself, over the same hop, inside the same
              deployment. A second secret would be a second thing to rotate for
              no boundary that actually differs.
        """
        return await self._announce_to(self.config.paid_url, bill_id, "paid")

    async def announce(self, bill_id: str) -> bool:
        """Tell the dispatcher that an invoice has been approved.

        Args:
            bill_id (str): The invoice that should go out.

        Returns:
            bool: ``True`` when the call was made and accepted, ``False`` when
            it was disabled, unconfigured or refused.

        Notes:
            - Carries an identifier and nothing else. The endpoint re-reads the
              invoice, so amounts on the wire would be a second copy of the
              document — one that could disagree with the stored one and decide
              what a customer is charged.
            - The two "off" cases are reported differently on purpose. Disabled
              is a decision and logs at debug; a secret that was never set is a
              misconfiguration — somebody switched the webhook on and stopped
              there — and says so at warning, naming the variable to set.
        """
        return await self._announce_to(self.config.url, bill_id, "approved")
