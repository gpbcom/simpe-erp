from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import Optional

# Third-party imports
import httpx

# First-party imports
from models.configuration.webhook_config import WebhookConfig


class PlanningWebhook:
    """Announces a finished planning run to whatever emails it.

    Attributes:
        config (WebhookConfig): Where to call, and with which shared secret.
        logger (Logger): Logger for announcements.

    Notes:
        - **This is the only thing that makes the dispatch automatic.** A
          planning run rewrites the week. The documents that follow it — every
          assistant's diary, every accepted quote — go out because this call is
          made. Without it the endpoint exists and nothing ever reaches it, and
          the failure is silent in both directions: no error is logged, and no
          mail arrives.
        - **A class in ``service``, called from two processes.** The API's
          in-process planning path and the worker both finish runs, and the
          worker deliberately does not depend on ``api`` — so the announcement
          cannot live in the API's dependency module, where it used to. One
          copy means the token, the timeout and the swallowing rule cannot
          drift between the two.
        - A failure is **logged and swallowed**. The planning succeeded and is
          already stored. An unreachable mailer must not turn a good run into a
          failed one, and the endpoint can be called by hand afterwards.
    """

    def __init__(self, config: WebhookConfig, logger: Optional[Logger] = None) -> None:
        """Initialize the announcer.

        Args:
            config (WebhookConfig): Where to call, and with which secret.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug(
            "PlanningWebhook created for %s (enabled=%s).",
            self.config.url,
            self.config.enabled,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    async def announce(self, run_id: str) -> bool:
        """Tell the dispatcher that a run succeeded.

        Args:
            run_id (str): The run whose documents should go out.

        Returns:
            bool: ``True`` when the call was made and accepted, ``False`` when
            it was disabled, unconfigured or refused.

        Notes:
            The two "off" cases are reported differently on purpose. Disabled
            is a decision and logs at debug. A secret that was never set is a
            misconfiguration — somebody switched the webhook on and stopped
            there — and says so at warning, naming the variable to set.
        """
        if not self.config.enabled:
            self.logger.debug(
                "The planning webhook is disabled. Not announcing %s.", run_id
            )
            return False
        token = self.config.get_token()
        if not token:
            self.logger.warning(
                "Not announcing planning run %s: the webhook secret (%s) is "
                "unset, so the documents will not be emailed.",
                run_id,
                self.config.token_env,
            )
            return False
        self.logger.info("Announcing planning run %s to %s.", run_id, self.config.url)
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                response = await client.post(
                    self.config.url,
                    json={"run_id": run_id},
                    headers={"X-Webhook-Token": token},
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            self.logger.error("Could not announce planning run %s: %s", run_id, exc)
            return False
        self.logger.info(
            "Planning run %s announced. The dispatcher answered %d.",
            run_id,
            response.status_code,
        )
        return True
