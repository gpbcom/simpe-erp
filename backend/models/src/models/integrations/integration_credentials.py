from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional

# Third-party imports
from pydantic import BaseModel, ConfigDict, Field, field_validator

# First-party imports
from models.integrations.exceptions import (
    MTIntegrationCredentialsInvalidAccountId,
    MTIntegrationCredentialsInvalidApiKey,
    MTIntegrationCredentialsInvalidBaseUrl,
    MTIntegrationCredentialsInvalidLegalEntityId,
)


class IntegrationCredentials(BaseModel):
    """What a platform needs to believe a request came from this agency.

    Attributes:
        MIN_KEY_LENGTH (ClassVar[int]): Shortest key accepted.
        MAX_KEY_LENGTH (ClassVar[int]): Longest key accepted.
        MAX_REFERENCE_LENGTH (ClassVar[int]): Longest account reference.
        HINT_LENGTH (ClassVar[int]): Characters of the key kept for the screen.
        REDACTED (ClassVar[str]): What stands in for the secret in any text.
        HTTPS (ClassVar[str]): The only scheme a base URL may use.
        api_key (str): The secret the platform authenticates on.
        account_id (Optional[str]): The account a request is made against.
        legal_entity_id (Optional[str]): The sender registered with a platform.
        base_url (Optional[str]): An override for the platform's own address.

    Notes:
        - **This model exists in memory and nowhere else.** It is built when a
          manager types a key, encrypted immediately, and rebuilt only inside a
          connector about to make a call. It is never a response body, never a
          column, and never a field on another model — the stored form is the
          ciphertext on
          :class:`~models.integrations.einvoicing_integration.EInvoicingIntegration`.
        - **Both ``__repr__`` and ``__str__`` are overridden**, which no other
          model here does. Pydantic's default prints every field, so a secret on
          an ordinary model reaches the log the first time anything formats it —
          an exception's ``repr`` of its arguments, a debug line, a traceback
          frame. The two together close the paths that do not go through
          :meth:`model_dump`.
        - The fields beyond ``api_key`` are optional because the four platforms
          disagree about what identifies an account: B2Brouter routes on an
          account in the path, Storecove on a ``legalEntityId`` created in its
          console, and Invopop and Iopole on the key alone. Which ones a given
          platform wants is declared by
          :class:`~models.integrations.provider_descriptor.ProviderDescriptor`
          rather than guessed here.
        - ``base_url`` exists so a sandbox can be pointed at without a release.
          It is restricted to HTTPS because every request made with it carries
          the key.
    """

    MIN_KEY_LENGTH: ClassVar[int] = 8
    MAX_KEY_LENGTH: ClassVar[int] = 512
    MAX_REFERENCE_LENGTH: ClassVar[int] = 128
    HINT_LENGTH: ClassVar[int] = 4
    REDACTED: ClassVar[str] = "IntegrationCredentials(api_key=<redacted>)"
    HTTPS: ClassVar[str] = "https://"

    model_config = ConfigDict(extra="forbid", frozen=True)

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
        """Validates that ``api_key`` is a plausible secret.

        Args:
            value (Optional[str]): Raw key.

        Returns:
            str: The stripped key.

        Raises:
            MTIntegrationCredentialsInvalidApiKey: If ``value`` is not a
                non-empty string of a plausible length.

        Notes:
            - **The message names no value**, unlike every other validator in this
              codebase. A 422 that quotes what it refused is what makes the others
              actionable; here the refused value is the secret, and quoting it
              would write it into the application log on the way out.
            - The floor is a typo check rather than a security control — a
              two-character key is a paste that went wrong, and catching it here
              saves a round trip to a platform that would answer 401.
        """
        if value is None or not isinstance(value, str) or not value.strip():
            raise MTIntegrationCredentialsInvalidApiKey(
                "Invalid api_key: a non-empty key is required."
            )
        stripped = value.strip()
        if not cls.MIN_KEY_LENGTH <= len(stripped) <= cls.MAX_KEY_LENGTH:
            raise MTIntegrationCredentialsInvalidApiKey(
                f"Invalid api_key: must be between {cls.MIN_KEY_LENGTH} and "
                f"{cls.MAX_KEY_LENGTH} characters."
            )
        return stripped

    @field_validator("account_id", mode="before")
    def validate_account_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``account_id``, when given, is usable text.

        Args:
            value (Optional[str]): Raw account reference.

        Returns:
            Optional[str]: The stripped reference, or ``None``.

        Raises:
            MTIntegrationCredentialsInvalidAccountId: If ``value`` is neither
                ``None`` nor a non-empty string of bounded length.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTIntegrationCredentialsInvalidAccountId(
                f"Invalid account_id: {value!r}. Must be a non-empty string."
            )
        stripped = value.strip()
        if len(stripped) > cls.MAX_REFERENCE_LENGTH:
            raise MTIntegrationCredentialsInvalidAccountId(
                f"Invalid account_id: longer than {cls.MAX_REFERENCE_LENGTH}."
            )
        return stripped

    @field_validator("legal_entity_id", mode="before")
    def validate_legal_entity_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``legal_entity_id``, when given, is usable text.

        Args:
            value (Optional[str]): Raw legal-entity reference.

        Returns:
            Optional[str]: The stripped reference, or ``None``.

        Raises:
            MTIntegrationCredentialsInvalidLegalEntityId: If ``value`` is
                neither ``None`` nor a non-empty string of bounded length.

        Notes:
            Storecove creates this in its own console rather than through its
            API, so it is something a manager copies across rather than
            something this application can fetch.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTIntegrationCredentialsInvalidLegalEntityId(
                f"Invalid legal_entity_id: {value!r}. Must be a non-empty string."
            )
        stripped = value.strip()
        if len(stripped) > cls.MAX_REFERENCE_LENGTH:
            raise MTIntegrationCredentialsInvalidLegalEntityId(
                f"Invalid legal_entity_id: longer than {cls.MAX_REFERENCE_LENGTH}."
            )
        return stripped

    @field_validator("base_url", mode="before")
    def validate_base_url(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``base_url``, when given, is an absolute HTTPS address.

        Args:
            value (Optional[str]): Raw address.

        Returns:
            Optional[str]: The address without its trailing slash, or ``None``.

        Raises:
            MTIntegrationCredentialsInvalidBaseUrl: If ``value`` is neither
                ``None`` nor an absolute HTTPS address.

        Notes:
            - Plain HTTP is refused rather than upgraded. Every request made with
              this address carries the API key, and quietly rewriting a configured
              host is how an operator comes to believe they are talking to one
              they are not.
            - The trailing slash is dropped so a connector can join paths without
              each one having to guess whether it is already there.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTIntegrationCredentialsInvalidBaseUrl(
                f"Invalid base_url: {value!r}. Must be a non-empty string."
            )
        stripped = value.strip()
        if not stripped.startswith(cls.HTTPS):
            raise MTIntegrationCredentialsInvalidBaseUrl(
                f"Invalid base_url: {stripped!r}. Must start with {cls.HTTPS!r}."
            )
        return stripped.rstrip("/")

    ############################
    # Publicly Exposed Methods #
    ############################

    def hint(self) -> str:
        """Return the masked tail of the key, for a screen to show.

        Returns:
            str: An ellipsis and the last few characters of the key.

        Notes:
            This is the only part of a credential that is ever allowed out of
            the backend. It answers "is something configured, and is it the one
            I pasted?" without answering "what is it" — enough for a manager to
            recognise their own key and useless to anybody else.
        """
        return f"…{self.api_key[-self.HINT_LENGTH :]}"

    def __repr__(self) -> str:
        """Return a representation that carries no secret.

        Returns:
            str: A fixed redacted string.
        """
        return self.REDACTED

    def __str__(self) -> str:
        """Return a representation that carries no secret.

        Returns:
            str: A fixed redacted string.
        """
        return self.REDACTED
