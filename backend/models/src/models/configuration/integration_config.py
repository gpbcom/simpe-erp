from __future__ import annotations

# Standard library imports
import os
from typing import ClassVar, List, Optional, Sequence, Tuple, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator

# First-party imports
from models.configuration.exceptions import (
    MTIntegrationConfigInvalidKeyEnv,
    MTIntegrationConfigInvalidProviders,
    MTIntegrationConfigInvalidTimeout,
    MTIntegrationConfigMissingKey,
    MTIntegrationConfigProviderUnknown,
)
from models.enums import EInvoicingProvider
from models.integrations.provider_descriptor import ProviderDescriptor


class IntegrationConfig(BaseModel):
    """Who the certified platforms are, and how this deployment talks to them.

    Attributes:
        MIN_TIMEOUT_SECONDS (ClassVar[float]): Shortest timeout accepted.
        MAX_TIMEOUT_SECONDS (ClassVar[float]): Longest timeout accepted.
        credential_key_env (str): Name of the environment variable holding the
            key stored credentials are encrypted with.
        request_timeout_seconds (float): How long to wait on a platform.
        providers (Tuple[ProviderDescriptor, ...]): The platforms this
            deployment offers, in the order the gallery shows them.

    Notes:
        - **The catalogue is configuration, not code.** Which platforms an
          agency may connect to is a deployment decision that changes when the
          registry does — a platform loses its registration, or a fifth
          publishes an API — and a list compiled into the image makes that a
          release. It is read from the ``integrations.providers`` block of
          ``app.yaml``; ``tests/models/configuration/test_integration_config.py``
          asserts the shipped file still declares every platform there is a
          connector for, which is what a bare default cannot promise.
        - **This is the single statement of who the platforms are.** The
          gallery, the enable dialog and the transmission service all read it,
          so a fact about a vendor is written once. Duplicating a display name
          or a coverage claim into TypeScript is how the screen and the server
          come to disagree about what an agency has connected to.
        - Coverage should be declared conservatively. Where a platform's own
          documentation does not mention a route, it is best *not* claimed:
          Storecove documents French e-reporting but says nothing about Chorus
          Pro, and an entry that assumed it would send a département's invoice
          into silence. Absent evidence, refusing is the recoverable error.
        - **The key is named here and held in the environment**, exactly as
          :class:`~models.configuration.auth_config.AuthConfig` names the JWT
          secret. A key in a configuration file is a key in the image and in
          version control; a key in the environment is one a deployment injects
          from its own secret store.
        - **There is deliberately no default key.** A fallback would let the
          service boot in production encrypting every agency's platform
          credentials with a value that is public knowledge — worse than
          refusing to start, because nothing about it looks wrong.
        - Losing the key means every stored credential must be re-entered. That
          is the price of being able to read them back at all, and it is why
          :attr:`~models.integrations.einvoicing_integration.EInvoicingIntegration.credential_hint`
          is stored beside the ciphertext rather than derived from it — after a
          key loss the hints still say which key was configured where.
        - The timeout is bounded because a platform that never answers must not
          hold a worker open. Transmission happens off the manager's click, so a
          slow platform costs a retry rather than a request.
    """

    MIN_TIMEOUT_SECONDS: ClassVar[float] = 1.0
    MAX_TIMEOUT_SECONDS: ClassVar[float] = 120.0

    credential_key_env: str = Field(
        default="EINVOICING_CREDENTIAL_KEY",
        description="Environment variable holding the credential encryption key.",
    )
    request_timeout_seconds: float = Field(
        default=30.0,
        description="How long to wait on a certified platform.",
    )
    providers: Tuple[ProviderDescriptor, ...] = Field(
        default=(),
        description="The certified platforms this deployment offers.",
    )

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("credential_key_env", mode="before")
    def validate_credential_key_env(cls, value: Optional[str]) -> str:
        """Validates that ``credential_key_env`` names an environment variable.

        Args:
            value (Optional[str]): Raw variable name.

        Returns:
            str: The stripped variable name.

        Raises:
            MTIntegrationConfigInvalidKeyEnv: If ``value`` is not a non-empty
                string.

        Notes:
            The *name* is configuration and the value is a secret. Keeping them
            apart is what lets this field sit in ``app.yaml`` in the open.
        """
        if value is None or not isinstance(value, str) or not value.strip():
            raise MTIntegrationConfigInvalidKeyEnv(
                f"Invalid credential_key_env: {value!r}. Must be a non-empty "
                f"string naming an environment variable."
            )
        return value.strip()

    @field_validator("request_timeout_seconds", mode="before")
    def validate_request_timeout_seconds(
        cls, value: Optional[Union[int, float, str]]
    ) -> float:
        """Validates that the platform timeout is within the accepted range.

        Args:
            value (Optional[Union[int, float, str]]): Raw timeout.

        Returns:
            float: The validated timeout.

        Raises:
            MTIntegrationConfigInvalidTimeout: If ``value`` is missing or
                outside the accepted range.

        Notes:
            The floor exists because a sub-second timeout would fail against
            every real platform; the ceiling because a platform that never
            answers must not hold a worker open indefinitely.
        """
        if value is None:
            raise MTIntegrationConfigInvalidTimeout(
                "Invalid request_timeout_seconds: a timeout is required."
            )
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise MTIntegrationConfigInvalidTimeout(
                f"Invalid request_timeout_seconds: {value!r}. Must be a number."
            )
        try:
            coerced = float(value)
        except (TypeError, ValueError):
            raise MTIntegrationConfigInvalidTimeout(
                f"Invalid request_timeout_seconds: {value!r}. Must be a number."
            ) from None
        if not cls.MIN_TIMEOUT_SECONDS <= coerced <= cls.MAX_TIMEOUT_SECONDS:
            raise MTIntegrationConfigInvalidTimeout(
                f"Invalid request_timeout_seconds: {coerced!r}. Must be within "
                f"{cls.MIN_TIMEOUT_SECONDS}..{cls.MAX_TIMEOUT_SECONDS}."
            )
        return coerced

    @field_validator("providers", mode="before")
    def validate_providers(
        cls, value: Optional[Sequence[Union[ProviderDescriptor, JsonValue]]]
    ) -> Tuple[ProviderDescriptor, ...]:
        """Validates that the declared platform catalogue is usable.

        Args:
            value (Optional[Sequence[Union[ProviderDescriptor, JsonValue]]]):
                Raw entries, as mappings from ``app.yaml`` or as already-built
                descriptors.

        Returns:
            Tuple[ProviderDescriptor, ...]: The catalogue, in declared order.

        Raises:
            MTIntegrationConfigInvalidProviders: If the payload is not a list of
                entries, or declares the same platform twice.

        Notes:
            - Each entry's own fields are validated by
              :class:`~models.integrations.provider_descriptor.ProviderDescriptor`,
              which raises its own ``MT*`` for a bad name, address or coverage.
              This validator only owns what a *list* can get wrong.
            - **Duplicates are refused rather than deduplicated.** Two entries
              for one platform means somebody edited the configuration and meant
              one of them; guessing which would show a card whose documentation
              link and coverage came from different lines of the file.
            - An empty catalogue is accepted: a deployment that offers no
              platform is a deployment that has not been configured yet, and
              refusing to build the object would take the whole application down
              rather than the one screen that needs it.
        """
        if value is None:
            return ()
        if isinstance(value, (str, bytes, dict)):
            raise MTIntegrationConfigInvalidProviders(
                f"Invalid providers: {value!r}. Must be a list of platform entries."
            )
        try:
            declared = list(value)
        except TypeError:
            raise MTIntegrationConfigInvalidProviders(
                f"Invalid providers: {value!r}. Must be a list of platform entries."
            ) from None
        entries: List[ProviderDescriptor] = []
        seen: List[EInvoicingProvider] = []
        for entry in declared:
            built = (
                entry
                if isinstance(entry, ProviderDescriptor)
                else ProviderDescriptor.model_validate(entry)
            )
            if built.provider in seen:
                raise MTIntegrationConfigInvalidProviders(
                    f"Invalid providers: {built.provider.value!r} is declared "
                    f"more than once."
                )
            seen.append(built.provider)
            entries.append(built)
        return tuple(entries)

    ############################
    # Publicly Exposed Methods #
    ############################

    def all_providers(self) -> Tuple[ProviderDescriptor, ...]:
        """Return every platform, in the order the gallery shows them.

        Returns:
            Tuple[ProviderDescriptor, ...]: The declared platforms.

        Notes:
            Order is the order of the configuration file rather than
            alphabetical. The gallery offers its own sort control, so this only
            decides what an agency sees before it chooses one.
        """
        return self.providers

    def describe_provider(self, provider: EInvoicingProvider) -> ProviderDescriptor:
        """Return the declared entry for one platform.

        Args:
            provider (EInvoicingProvider): The platform wanted.

        Returns:
            ProviderDescriptor: What this deployment says about it.

        Raises:
            MTIntegrationConfigProviderUnknown: If the catalogue has no entry.

        Notes:
            Compared by value, not identity.
            :class:`~models.enums.EInvoicingProvider` is a ``StrEnum``, so a
            caller holding a path parameter has the string ``"storecove"``
            rather than the member — and an identity check would refuse it while
            reporting that the platform was not configured, which is both wrong
            and the most misleading message available.
        """
        for entry in self.providers:
            if entry.provider == provider:
                return entry
        raise MTIntegrationConfigProviderUnknown(
            f"No platform {provider!r} is configured. The deployment's "
            f"integrations.providers block declares: "
            f"{', '.join(entry.provider.value for entry in self.providers)}."
        )

    def get_credential_key(self) -> str:
        """Return the credential encryption key from the environment.

        Returns:
            str: The resolved key.

        Raises:
            MTIntegrationConfigMissingKey: If the environment variable named by
                ``credential_key_env`` is unset or empty.

        Notes:
            There is deliberately no default. A fallback key would encrypt every
            agency's platform credentials with a value anybody reading this
            repository could recover.
        """
        key = os.environ.get(self.credential_key_env, "")
        if not key:
            raise MTIntegrationConfigMissingKey(
                f"Environment variable {self.credential_key_env!r} is not set. "
                f"It must hold the credential encryption key."
            )
        return key
