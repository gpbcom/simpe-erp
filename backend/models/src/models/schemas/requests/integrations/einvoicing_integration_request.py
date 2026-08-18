from __future__ import annotations

# Standard library imports
from typing import Optional

# Third-party imports
from pydantic import BaseModel, ConfigDict, Field, field_validator

# First-party imports
from models.integrations.integration_credentials import IntegrationCredentials
from models.schemas.exceptions import (
    MTEInvoicingIntegrationRequestInvalidField,
)


class EInvoicingIntegrationRequest(BaseModel):
    """What the enable dialog sends when a manager connects a platform.

    Attributes:
        api_key (str): The secret the platform authenticates on.
        account_id (Optional[str]): The account a request is made against.
        legal_entity_id (Optional[str]): The sender registered with a platform.
        base_url (Optional[str]): An override for the platform's own address.

    Notes:
        - **The platform is not in the payload.** It is in the path, so a body
          naming a different one cannot disagree with the URL a manager clicked.
        - **Mirrors :class:`~models.integrations.integration_credentials.IntegrationCredentials`
          rather than embedding it**, so the wire format is a flat object the
          dialog can build field by field, and the credentials model stays the
          thing that only ever exists in memory.
        - ``model_config`` forbids extras. A typo'd field on a secret-bearing
          payload would be dropped silently, and the connector would then
          authenticate with less than the manager believed they had sent.
        - Every value is validated by building the credentials, so the rules
          live in one place — including the one that matters most: the refusal
          message never quotes the key.
    """

    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(description="The secret the platform authenticates on.")
    account_id: Optional[str] = Field(
        default=None,
        description="The account a request is made against.",
    )
    legal_entity_id: Optional[str] = Field(
        default=None,
        description="The sender registered with a platform.",
    )
    base_url: Optional[str] = Field(
        default=None,
        description="An override for the platform's own address.",
    )

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("api_key", mode="before")
    def validate_api_key(cls, value: Optional[str]) -> str:
        """Validates that ``api_key`` is present.

        Args:
            value (Optional[str]): Raw key.

        Returns:
            str: The key, unchanged.

        Raises:
            MTEInvoicingIntegrationRequestInvalidField: If ``value`` is not a
                string.

        Notes:
            Only the type is checked here. The shape is checked by
            :meth:`credentials`, which is what builds the model that owns the
            rule. Two copies of "how long may a key be" would drift, and this
            one would be the copy nobody updated.
        """
        if value is None or not isinstance(value, str):
            raise MTEInvoicingIntegrationRequestInvalidField(
                "Invalid api_key: a key is required."
            )
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def credentials(self) -> IntegrationCredentials:
        """Return the payload as the credentials a connector uses.

        Returns:
            IntegrationCredentials: The validated credentials.

        Raises:
            MTInvalidIntegrationCredentialsException: If any value is not
                usable, with a message that never quotes the key.
        """
        return IntegrationCredentials(
            api_key=self.api_key,
            account_id=self.account_id,
            legal_entity_id=self.legal_entity_id,
            base_url=self.base_url,
        )
