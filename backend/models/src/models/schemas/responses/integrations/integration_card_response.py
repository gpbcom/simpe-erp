from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import List, Optional

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import EInvoicingProvider, TransmissionKind
from models.integrations.einvoicing_integration import EInvoicingIntegration
from models.integrations.provider_descriptor import ProviderDescriptor
from models.schemas.exceptions import MTIntegrationCardResponseInvalidProvider


class IntegrationCardResponse(BaseModel):
    """One card in the integrations gallery: a platform, and where we stand with it.

    Attributes:
        provider (EInvoicingProvider): The platform.
        name (str): What it is called.
        home_url (str): Its own site.
        documentation_url (str): Where its API is documented.
        coverage (List[TransmissionKind]): What it can be asked to send.
        required_fields (List[str]): Which credentials the dialog must ask for.
        documentation_verified (bool): Whether its API docs were read directly.
        configured (bool): Whether this agency has stored credentials for it.
        enabled (bool): Whether invoices are transmitted through it.
        credential_hint (str): The masked tail of the stored key.
        last_checked_at (Optional[datetime]): When the key was last proven.
        last_check_error (Optional[str]): Why the last check failed, if it did.

    Notes:
        - **One shape for a platform an agency has never touched and one it
          transmits through daily.** The gallery renders four cards either way,
          so a response that omitted the unconfigured ones would make the client
          merge two lists and invent the difference.
        - **``credential_ciphertext`` is deliberately absent**, and this is the
          class that makes that true rather than a rule somebody remembers. The
          screen gets ``credential_hint`` — enough for a manager to recognise
          their own key and useless to anybody else. There is no endpoint that
          returns the secret.
        - ``documentation_verified`` is carried through to the card because a
          gallery offering four platforms as equals would be lying by omission
          about the one whose API nobody here could read.
    """

    provider: EInvoicingProvider = Field(description="The platform.")
    name: str = Field(description="What it is called.")
    home_url: str = Field(description="Its own site.")
    documentation_url: str = Field(description="Where its API is documented.")
    coverage: List[TransmissionKind] = Field(
        default_factory=list,
        description="What it can be asked to send.",
    )
    required_fields: List[str] = Field(
        default_factory=list,
        description="Which credentials the dialog must ask for.",
    )
    documentation_verified: bool = Field(
        default=False,
        description="Whether its API documentation was read directly.",
    )
    configured: bool = Field(
        default=False,
        description="Whether this agency has stored credentials for it.",
    )
    enabled: bool = Field(
        default=False,
        description="Whether invoices are transmitted through it.",
    )
    credential_hint: str = Field(
        default="",
        description="The masked tail of the stored key.",
    )
    last_checked_at: Optional[datetime] = Field(
        default=None,
        description="When the key was last proven.",
    )
    last_check_error: Optional[str] = Field(
        default=None,
        description="Why the last check failed, if it did.",
    )

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("provider", mode="before")
    def validate_provider(cls, value: Optional[object]) -> EInvoicingProvider:
        """Validates that ``provider`` names a supported platform.

        Args:
            value (Optional[object]): Raw platform.

        Returns:
            EInvoicingProvider: The coerced platform.

        Raises:
            MTIntegrationCardResponseInvalidProvider: If ``value`` is missing or
                unknown.
        """
        if value is None:
            raise MTIntegrationCardResponseInvalidProvider(
                "Invalid provider: a platform is required."
            )
        if isinstance(value, EInvoicingProvider):
            return value
        try:
            return EInvoicingProvider(value)
        except (ValueError, TypeError):
            raise MTIntegrationCardResponseInvalidProvider(
                f"Invalid provider: {value!r}. Must be one of: "
                f"{', '.join(EInvoicingProvider.values())}."
            ) from None

    ############################
    # Publicly Exposed Methods #
    ############################

    @classmethod
    def describing(
        cls,
        descriptor: ProviderDescriptor,
        integration: Optional[EInvoicingIntegration],
    ) -> IntegrationCardResponse:
        """Return the card for a platform and this agency's state with it.

        Args:
            descriptor (ProviderDescriptor): What is true of the platform for
                everybody.
            integration (Optional[EInvoicingIntegration]): What this agency has
                configured, or ``None``.

        Returns:
            IntegrationCardResponse: The card.

        Notes:
            Built here rather than in the service so that the one place that
            decides what leaves the backend is the class that defines the
            payload. A service assembling this by hand is a service that can
            forget which field is the secret.
        """
        return IntegrationCardResponse(
            provider=descriptor.provider,
            name=descriptor.name,
            home_url=descriptor.home_url,
            documentation_url=descriptor.documentation_url,
            coverage=list(descriptor.coverage),
            required_fields=list(descriptor.required_fields),
            documentation_verified=descriptor.documentation_verified,
            configured=integration is not None,
            enabled=integration.enabled if integration else False,
            credential_hint=integration.credential_hint if integration else "",
            last_checked_at=integration.last_checked_at if integration else None,  # noqa: E501
            last_check_error=integration.last_check_error if integration else None,  # noqa: E501
        )
