from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import EInvoicingProvider
from models.integrations.exceptions import (
    MTEInvoicingIntegrationInvalidCiphertext,
    MTEInvoicingIntegrationInvalidCompany,
    MTEInvoicingIntegrationInvalidDate,
    MTEInvoicingIntegrationInvalidEnabled,
    MTEInvoicingIntegrationInvalidError,
    MTEInvoicingIntegrationInvalidHint,
    MTEInvoicingIntegrationInvalidId,
    MTEInvoicingIntegrationInvalidProvider,
)


class EInvoicingIntegration(BaseModel):
    """An agency's contract with one certified platform, as this system holds it.

    Attributes:
        MAX_HINT_LENGTH (ClassVar[int]): Longest accepted credential hint.
        MAX_ERROR_LENGTH (ClassVar[int]): Longest recorded check failure.
        id (str): Identifier.
        company_id (str): The agency this belongs to.
        provider (EInvoicingProvider): The platform.
        enabled (bool): Whether invoices are transmitted through it.
        credential_ciphertext (str): The encrypted credentials.
        credential_hint (str): The masked tail of the key, for the screen.
        created_at (Optional[datetime]): When it was first configured.
        updated_at (Optional[datetime]): When it was last changed.
        updated_by (Optional[str]): The account that last changed it.
        last_checked_at (Optional[datetime]): When the key was last proven.
        last_check_error (Optional[str]): Why the last check failed, if it did.

    Notes:
        - **The secret is here only as ciphertext, and that is the whole design.**
          A connector needs the key back, so hashing it is not an option — but
          nothing outside
          :class:`~service.security.credential_cipher.CredentialCipher` may hold
          the plaintext, and no response body ever carries this field. What a
          screen gets instead is ``credential_hint``.
        - **Enabled is a fact about this row, not about the agency.** At most one
          row per agency may carry ``True``, and that invariant is enforced by
          the repository in the same transaction as the write — a model can
          state the rule but cannot see its siblings, and two concurrent enables
          would otherwise both believe they were the only one.
        - ``last_checked_at`` and ``last_check_error`` are kept because a
          credential that worked in the dialog can stop working later — a key
          rotated at the platform, a subscription lapsed. Without them the first
          sign would be a paid invoice that silently never left, which is the
          failure this whole feature exists to prevent.
        - There is no ``deleted``. Disabling is what stops transmission, and
          keeping the row keeps the hint and the history of what was once
          configured — useful precisely when somebody asks where last quarter's
          invoices went.
    """

    MAX_HINT_LENGTH: ClassVar[int] = 16
    MAX_ERROR_LENGTH: ClassVar[int] = 512

    id: str = Field(description="Identifier.")
    company_id: str = Field(description="The agency this belongs to.")
    provider: EInvoicingProvider = Field(description="The platform.")
    enabled: bool = Field(
        default=False,
        description="Whether invoices are transmitted through it.",
    )
    credential_ciphertext: str = Field(description="The encrypted credentials.")
    credential_hint: str = Field(
        default="",
        description="The masked tail of the key, for the screen.",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="When it was first configured.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="When it was last changed.",
    )
    updated_by: Optional[str] = Field(
        default=None,
        description="The account that last changed it.",
    )
    last_checked_at: Optional[datetime] = Field(
        default=None,
        description="When the key was last proven against the platform.",
    )
    last_check_error: Optional[str] = Field(
        default=None,
        description="Why the last check failed, if it did.",
    )

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> str:
        """Validates that ``id`` is a non-empty identifier.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTEInvoicingIntegrationInvalidId: If ``value`` is not a non-empty
                string.
        """
        if value is None or not isinstance(value, str) or not value.strip():
            raise MTEInvoicingIntegrationInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("company_id", mode="before")
    def validate_company_id(cls, value: Optional[str]) -> str:
        """Validates that ``company_id`` names the owning agency.

        Args:
            value (Optional[str]): Raw agency identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTEInvoicingIntegrationInvalidCompany: If ``value`` is not a
                non-empty string.

        Notes:
            An integration with no agency would be visible to every tenant, and
            it holds the credentials of a platform account somebody pays for.
        """
        if value is None or not isinstance(value, str) or not value.strip():
            raise MTEInvoicingIntegrationInvalidCompany(
                f"Invalid company_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("provider", mode="before")
    def validate_provider(
        cls, value: Optional[Union[str, EInvoicingProvider]]
    ) -> EInvoicingProvider:
        """Validates that ``provider`` names a supported platform.

        Args:
            value (Optional[Union[str, EInvoicingProvider]]): Raw platform.

        Returns:
            EInvoicingProvider: The coerced platform.

        Raises:
            MTEInvoicingIntegrationInvalidProvider: If ``value`` is missing or
                is not a supported platform.

        Notes:
            There is no default. Every other field here describes *how* an
            integration is configured. This one says which platform the
            credentials belong to, and guessing it would send an agency's
            invoices to a company it has no contract with.
        """
        if value is None:
            raise MTEInvoicingIntegrationInvalidProvider(
                "Invalid provider: a platform is required."
            )
        if isinstance(value, EInvoicingProvider):
            return value
        try:
            return EInvoicingProvider(value)
        except ValueError:
            raise MTEInvoicingIntegrationInvalidProvider(
                f"Invalid provider: {value!r}. Must be one of: "
                f"{', '.join(EInvoicingProvider.values())}."
            ) from None

    @field_validator("enabled", mode="before")
    def validate_enabled(cls, value: Optional[bool]) -> bool:
        """Validates that ``enabled`` is a boolean.

        Args:
            value (Optional[bool]): Raw flag.

        Returns:
            bool: The flag; ``None`` reads as off.

        Raises:
            MTEInvoicingIntegrationInvalidEnabled: If ``value`` is neither
                ``None`` nor a boolean.

        Notes:
            ``None`` reads as off rather than raising, so a row written before
            the column existed is disabled rather than unreadable. A truthy
            string is refused: ``"false"`` is truthy, and reading it as "on"
            would transmit an agency's invoices on the strength of a typo.
        """
        if value is None:
            return False
        if not isinstance(value, bool):
            raise MTEInvoicingIntegrationInvalidEnabled(
                f"Invalid enabled: {value!r}. Must be a boolean."
            )
        return value

    @field_validator("credential_ciphertext", mode="before")
    def validate_credential_ciphertext(cls, value: Optional[str]) -> str:
        """Validates that the stored credentials are present.

        Args:
            value (Optional[str]): Raw ciphertext.

        Returns:
            str: The stripped ciphertext.

        Raises:
            MTEInvoicingIntegrationInvalidCiphertext: If ``value`` is not a
                non-empty string.

        Notes:
            Only presence is checked. Whether the ciphertext decrypts is a
            question for the cipher holding the key, and a model that tried to
            answer it would need the key — which is exactly what keeping the
            secret out of this layer is for.
        """
        if value is None or not isinstance(value, str) or not value.strip():
            raise MTEInvoicingIntegrationInvalidCiphertext(
                "Invalid credential_ciphertext: encrypted credentials are required."
            )
        return value.strip()

    @field_validator("credential_hint", mode="before")
    def validate_credential_hint(cls, value: Optional[str]) -> str:
        """Validates that the credential hint is a short masked tail.

        Args:
            value (Optional[str]): Raw hint.

        Returns:
            str: The stripped hint, or an empty string.

        Raises:
            MTEInvoicingIntegrationInvalidHint: If ``value`` is not a string, or
                is long enough to hold a key.

        Notes:
            The bound is the point. The hint is the one part of a credential
            that leaves the backend, and a field long enough to carry the whole
            key would quietly undo the reason the ciphertext is withheld.
        """
        if value is None:
            return ""
        if not isinstance(value, str):
            raise MTEInvoicingIntegrationInvalidHint(
                f"Invalid credential_hint: {value!r}. Must be a string."
            )
        stripped = value.strip()
        if len(stripped) > cls.MAX_HINT_LENGTH:
            raise MTEInvoicingIntegrationInvalidHint(
                f"Invalid credential_hint: longer than {cls.MAX_HINT_LENGTH} "
                f"characters, which is long enough to leak the key."
            )
        return stripped

    @field_validator("updated_by", mode="before")
    def validate_updated_by(cls, value: Optional[str]) -> Optional[str]:
        """Validates that the editing account, when given, is identified.

        Args:
            value (Optional[str]): Raw account identifier.

        Returns:
            Optional[str]: The stripped identifier, or ``None``.

        Raises:
            MTEInvoicingIntegrationInvalidError: If ``value`` is neither
                ``None`` nor a non-empty string.

        Notes:
            "Who connected this platform?" is a question with a name attached —
            the account that did it accepted a contract on the agency's behalf.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTEInvoicingIntegrationInvalidError(
                f"Invalid updated_by: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("last_check_error", mode="before")
    def validate_last_check_error(cls, value: Optional[str]) -> Optional[str]:
        """Validates that a recorded check failure is usable text.

        Args:
            value (Optional[str]): Raw failure description.

        Returns:
            Optional[str]: The message, truncated to the bound, or ``None``.

        Raises:
            MTEInvoicingIntegrationInvalidError: If ``value`` is neither
                ``None`` nor a string.

        Notes:
            **Truncated rather than refused.** This field is written from a
            platform's own error response, which nobody here controls, and a
            row that could not be saved because a third party was verbose would
            lose the very diagnosis it was trying to keep.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTEInvoicingIntegrationInvalidError(
                f"Invalid last_check_error: {value!r}. Must be a string."
            )
        stripped = value.strip()
        if not stripped:
            return None
        return stripped[: cls.MAX_ERROR_LENGTH]

    @field_validator("created_at", "updated_at", "last_checked_at", mode="before")
    def validate_timestamps(
        cls, value: Optional[Union[datetime, str]]
    ) -> Optional[datetime]:
        """Validates that a timestamp is a datetime.

        Args:
            value (Optional[Union[datetime, str]]): Raw timestamp.

        Returns:
            Optional[datetime]: The timestamp, or ``None``.

        Raises:
            MTEInvoicingIntegrationInvalidDate: If ``value`` is neither ``None``
                nor a datetime or ISO-8601 string.
        """
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                raise MTEInvoicingIntegrationInvalidDate(
                    f"Invalid timestamp: {value!r}. "  # noqa: E501
                    "Must be an ISO-8601 datetime."
                ) from None
        raise MTEInvoicingIntegrationInvalidDate(
            f"Invalid timestamp: {value!r}. Must be a datetime."
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_usable(self) -> bool:
        """Return whether invoices may be transmitted through this integration.

        Returns:
            bool: ``True`` when it is enabled and its last check did not fail.

        Notes:
            A failed check does **not** disable the integration, and this is the
            distinction the two flags exist for: disabling is a manager's
            decision and survives, whereas a failed check is a fact about the
            last attempt that the next one may overturn. Asking this rather than
            reading ``enabled`` alone is what stops an invoice being handed to a
            platform that answered 401 an hour ago.
        """
        return self.enabled and self.last_check_error is None
