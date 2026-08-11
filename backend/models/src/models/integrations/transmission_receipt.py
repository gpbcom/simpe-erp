from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator, model_validator

# First-party imports
from models.enums import (  # noqa: E501
    EInvoicingProvider,
    TransmissionKind,
    TransmissionStatus,
)
from models.integrations.exceptions import (
    MTTransmissionReceiptContradictory,
    MTTransmissionReceiptInvalidError,
    MTTransmissionReceiptInvalidKind,
    MTTransmissionReceiptInvalidProvider,
    MTTransmissionReceiptInvalidReference,
    MTTransmissionReceiptInvalidStatus,
)


class TransmissionReceipt(BaseModel):
    """What a platform said when it was handed an invoice or a declaration.

    Attributes:
        MAX_REFERENCE_LENGTH (ClassVar[int]): Longest accepted reference.
        MAX_ERROR_LENGTH (ClassVar[int]): Longest recorded failure.
        provider (EInvoicingProvider): The platform that answered.
        kind (TransmissionKind): What was transmitted.
        status (TransmissionStatus): How far it reached.
        reference (Optional[str]): The platform's own identifier for it.
        error (Optional[str]): Why it failed, when it did.

    Notes:
        - **The connectors' one return type.** Four platforms answer in four
          shapes — a guid, a submission id, a job, a document — and every
          caller wants the same three facts: did it go, what does the platform
          call it, and if not, why. Normalising here is what lets the
          transmission service be written once.
        - ``reference`` is the single most valuable field months later. It is
          what an operator quotes to a platform's support desk, and without it
          "we sent it" is unfalsifiable.
        - **A receipt cannot be both sent and failed**, and
          :meth:`check_consistency` refuses the combination. A connector that
          caught an exception and forgot to set the status would otherwise
          report success with an error attached, and the recorded history would
          say an invoice both arrived and did not.
    """

    MAX_REFERENCE_LENGTH: ClassVar[int] = 255
    MAX_ERROR_LENGTH: ClassVar[int] = 512

    provider: EInvoicingProvider = Field(description="The platform that answered.")
    kind: TransmissionKind = Field(description="What was transmitted.")
    status: TransmissionStatus = Field(description="How far it reached.")
    reference: Optional[str] = Field(
        default=None,
        description="The platform's own identifier for the transmission.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Why it failed, when it did.",
    )

    ############################
    # Fields Validation Methods #
    ############################

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
            MTTransmissionReceiptInvalidProvider: If ``value`` is missing or
                unknown.
        """
        if value is None:
            raise MTTransmissionReceiptInvalidProvider(
                "Invalid provider: a platform is required."
            )
        if isinstance(value, EInvoicingProvider):
            return value
        try:
            return EInvoicingProvider(value)
        except ValueError:
            raise MTTransmissionReceiptInvalidProvider(
                f"Invalid provider: {value!r}. Must be one of: "
                f"{', '.join(EInvoicingProvider.values())}."
            ) from None

    @field_validator("kind", mode="before")
    def validate_kind(
        cls, value: Optional[Union[str, TransmissionKind]]
    ) -> TransmissionKind:
        """Validates that ``kind`` names a supported obligation.

        Args:
            value (Optional[Union[str, TransmissionKind]]): Raw kind.

        Returns:
            TransmissionKind: The coerced kind.

        Raises:
            MTTransmissionReceiptInvalidKind: If ``value`` is missing or
                unknown.

        Notes:
            No default. "What was sent?" answered by a guess is worse than
            unanswered — an invoice recorded as a payment declaration would
            satisfy an audit that should have failed.
        """
        if value is None:
            raise MTTransmissionReceiptInvalidKind(
                "Invalid kind: what was transmitted is required."
            )
        if isinstance(value, TransmissionKind):
            return value
        try:
            return TransmissionKind(value)
        except ValueError:
            raise MTTransmissionReceiptInvalidKind(
                f"Invalid kind: {value!r}. Must be one of: "
                f"{', '.join(TransmissionKind.values())}."
            ) from None

    @field_validator("status", mode="before")
    def validate_status(
        cls, value: Optional[Union[str, TransmissionStatus]]
    ) -> TransmissionStatus:
        """Validates that ``status`` names a known outcome.

        Args:
            value (Optional[Union[str, TransmissionStatus]]): Raw status.

        Returns:
            TransmissionStatus: The coerced status.

        Raises:
            MTTransmissionReceiptInvalidStatus: If ``value`` is missing or
                unknown.
        """
        if value is None:
            raise MTTransmissionReceiptInvalidStatus(
                "Invalid status: an outcome is required."
            )
        if isinstance(value, TransmissionStatus):
            return value
        try:
            return TransmissionStatus(value)
        except ValueError:
            raise MTTransmissionReceiptInvalidStatus(
                f"Invalid status: {value!r}. Must be one of: "
                f"{', '.join(TransmissionStatus.values())}."
            ) from None

    @field_validator("reference", mode="before")
    def validate_reference(cls, value: Optional[str]) -> Optional[str]:
        """Validates that a platform reference, when given, is usable text.

        Args:
            value (Optional[str]): Raw reference.

        Returns:
            Optional[str]: The stripped reference, or ``None``.

        Raises:
            MTTransmissionReceiptInvalidReference: If ``value`` is neither
                ``None`` nor a string of bounded length.

        Notes:
            Coerced from ``int`` because two of the four platforms answer with
            a numeric identifier. Refusing it would mean every connector
            stringifying its own response, which is the kind of duplication a
            shared receipt exists to remove.
        """
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise MTTransmissionReceiptInvalidReference(
                f"Invalid reference: {value!r}. Must be a string."
            )
        stripped = str(value).strip()
        if not stripped:
            return None
        if len(stripped) > cls.MAX_REFERENCE_LENGTH:
            raise MTTransmissionReceiptInvalidReference(
                f"Invalid reference: longer than {cls.MAX_REFERENCE_LENGTH}."
            )
        return stripped

    @field_validator("error", mode="before")
    def validate_error(cls, value: Optional[str]) -> Optional[str]:
        """Validates that a recorded failure is usable text.

        Args:
            value (Optional[str]): Raw failure description.

        Returns:
            Optional[str]: The message, truncated to the bound, or ``None``.

        Raises:
            MTTransmissionReceiptInvalidError: If ``value`` is neither ``None``
                nor a string.

        Notes:
            Truncated rather than refused, for the same reason the integration's
            own check failure is: this is written from a third party's response
            body, and losing the diagnosis because somebody was verbose is the
            worse outcome.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTTransmissionReceiptInvalidError(
                f"Invalid error: {value!r}. Must be a string."
            )
        stripped = value.strip()
        if not stripped:
            return None
        return stripped[: cls.MAX_ERROR_LENGTH]

    @model_validator(mode="after")
    def check_consistency(self) -> TransmissionReceipt:
        """Validates that the outcome and the diagnosis agree.

        Returns:
            TransmissionReceipt: The validated receipt.

        Raises:
            MTTransmissionReceiptContradictory: If the receipt reports success
                with a failure attached, or failure with nothing to explain it.

        Notes:
            - **The pair is only wrong together**, which is why this is a model
              validator rather than two field ones. A connector that caught an
              exception and forgot to set the status would report an invoice as
              both arrived and not arrived, and the stored history would be
              unusable precisely when somebody needed it.
            - A failure with no message is refused for the same reason: "it
              failed" with nothing after it is what makes an operator open the
              application log, which is the outcome this whole model exists to
              avoid.
        """
        if self.status is TransmissionStatus.SENT and self.error is not None:
            raise MTTransmissionReceiptContradictory(
                "Invalid receipt: a transmission "  # noqa: E501
                "cannot be sent and have failed."
            )
        if self.status is TransmissionStatus.FAILED and not self.error:
            raise MTTransmissionReceiptContradictory(
                "Invalid receipt: a failed transmission "  # noqa: E501
                "must say why it failed."
            )
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def succeeded(self) -> bool:
        """Return whether the platform accepted what it was handed.

        Returns:
            bool: ``True`` only for a sent transmission.
        """
        return self.status is TransmissionStatus.SENT
