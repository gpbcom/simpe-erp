from __future__ import annotations

# Standard library imports
import os
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.configuration.exceptions import (
    MTWebhookConfigInvalidEnvName,
    MTWebhookConfigInvalidTimeout,
    MTWebhookConfigInvalidUrl,
)


class WebhookConfig(BaseModel):
    """Settings for the webhook that dispatches a finished planning by email.

    Attributes:
        enabled (bool): Whether a finished planning run calls the webhook.
        url (str): The endpoint to call once a run succeeds.
        token_env (str): Name of the environment variable holding the shared
            secret sent as ``X-Webhook-Token`` and checked on the way in.
        timeout_seconds (float): How long to wait on the call.

    Notes:
        - The same secret guards both ends: the planning job sends it, the
          endpoint compares it. The endpoint is exempt from the bearer-token
          middleware — a webhook has no signed-in user to authenticate as — so
          this secret is the only thing standing between an anonymous caller
          and an operation that emails every assistant and every customer.
        - Pointing ``url`` at this application's own endpoint is the intended
          arrangement, not a workaround: the dispatch then runs as an ordinary
          request, with the same handlers, logging and failure reporting as
          everything else, instead of inside a background task nobody can see.
    """

    enabled: bool = Field(
        default=False,
        description="Whether a finished planning run calls the webhook.",
    )
    url: str = Field(
        default="http://localhost:8000/api/v1/webhooks/planning-completed",
        description="The endpoint called once a planning run succeeds.",
    )
    token_env: str = Field(
        default="PLANNING_WEBHOOK_TOKEN",
        description="Name of the env var holding the shared secret.",
    )
    timeout_seconds: float = Field(
        default=10.0,
        description="How long to wait on the webhook call, in seconds.",
    )

    @field_validator("url", mode="before")
    def validate_url(cls, value: Optional[str]) -> str:
        """Validates that ``url`` is an absolute HTTP URL.

        Args:
            value (Optional[str]): Raw ``url`` value.

        Returns:
            str: The URL without a trailing slash.

        Raises:
            MTWebhookConfigInvalidUrl: If ``value`` is not an ``http`` or
                ``https`` URL.
        """
        if not isinstance(value, str) or not value.strip().startswith(
            ("http://", "https://")
        ):
            raise MTWebhookConfigInvalidUrl(
                f"Invalid url: {value!r}. Must be an http or https URL."
            )
        return value.strip().rstrip("/")

    @field_validator("token_env", mode="before")
    def validate_token_env(cls, value: Optional[str]) -> str:
        """Validates that the secret is named rather than inlined.

        Args:
            value (Optional[str]): Raw environment-variable name.

        Returns:
            str: The stripped name.

        Raises:
            MTWebhookConfigInvalidEnvName: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTWebhookConfigInvalidEnvName(
                f"Invalid token_env: {value!r}. Must be a non-empty string "
                f"naming the variable that holds the secret."
            )
        return value.strip()

    @field_validator("timeout_seconds", mode="before")
    def validate_timeout_seconds(cls, value: Union[int, float, None]) -> float:
        """Validates that ``timeout_seconds`` is strictly positive.

        Args:
            value (Union[int, float, None]): Raw timeout, in seconds.

        Returns:
            float: The validated timeout.

        Raises:
            MTWebhookConfigInvalidTimeout: If ``value`` is not a strictly
                positive number.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MTWebhookConfigInvalidTimeout(
                f"Invalid timeout_seconds: {value!r}. Must be a strictly "
                f"positive number of seconds."
            )
        coerced = float(value)
        if coerced <= 0:
            raise MTWebhookConfigInvalidTimeout(
                f"Invalid timeout_seconds: {coerced!r}. Must be strictly positive."
            )
        return coerced

    ############################
    # Publicly Exposed Methods #
    ############################

    def get_token(self) -> str:
        """Return the shared secret from the environment.

        Returns:
            str: The secret, or an empty string when the variable is unset.

        Notes:
            Never logged. An unset secret leaves the endpoint refusing every
            call, which is the safe direction: a webhook nobody can reach beats
            a webhook anybody can.
        """
        return os.environ.get(self.token_env, "")
