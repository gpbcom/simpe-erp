from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import Optional

# First-party imports
from models.integrations.einvoicing_integration import EInvoicingIntegration
from storage.mappers.base_mapper import BaseMapper
from storage.orm.integrations.einvoicing_integration_row import (
    EInvoicingIntegrationRow,
)


class EInvoicingIntegrationMapper(
    BaseMapper[EInvoicingIntegration, EInvoicingIntegrationRow]
):
    """Converts between :class:`EInvoicingIntegration` and its row.

    Notes:
        - **Nothing here decrypts anything.** The ciphertext travels between the
          row and the model untouched; only
          :class:`~service.security.credential_cipher.CredentialCipher` holds
          the key. A mapper that opened credentials would put the plaintext in
          every read, including the list the gallery renders.
        - Neither direction logs a hint or a ciphertext. The hint is harmless on
          a screen and pointless in a log, and the ciphertext is the last thing
          standing between a log reader and the key if it ever leaks.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(
            model_class=EInvoicingIntegration,
            row_class=EInvoicingIntegrationRow,
            logger=logger,
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_model(self, row: EInvoicingIntegrationRow) -> EInvoicingIntegration:
        """Build the integration from a row's columns.

        Args:
            row (EInvoicingIntegrationRow): The row to read.

        Returns:
            EInvoicingIntegration: The domain model.

        Raises:
            MTInvalidEInvoicingIntegrationException: If a stored value no
                longer satisfies the model's validators.
        """
        self.logger.debug(
            "Building integration %s for agency %s (%s, enabled=%s).",
            row.id,
            row.company_id,
            row.provider,
            row.enabled,
        )
        return EInvoicingIntegration(
            id=row.id,
            company_id=row.company_id,
            provider=row.provider,
            enabled=row.enabled,
            credential_ciphertext=row.credential_ciphertext,
            credential_hint=row.credential_hint,
            created_at=self.timestamps.to_utc(row.created_at),
            updated_at=self.timestamps.to_utc(row.updated_at),
            updated_by=row.updated_by,
            last_checked_at=self.timestamps.to_utc(row.last_checked_at),
            last_check_error=row.last_check_error,
        )

    def _apply_fields(
        self, row: EInvoicingIntegrationRow, model: EInvoicingIntegration
    ) -> None:
        """Write the integration onto a row's columns.

        Args:
            row (EInvoicingIntegrationRow): The row to write to.
            model (EInvoicingIntegration): The model carrying the values.
        """
        self.logger.debug(
            "Applying integration %s to row: %s, enabled=%s.",
            model.id,
            model.provider.value,
            model.enabled,
        )
        row.company_id = model.company_id
        row.provider = model.provider.value
        row.enabled = model.enabled
        row.credential_ciphertext = model.credential_ciphertext
        row.credential_hint = model.credential_hint
        row.updated_by = model.updated_by
        row.last_checked_at = model.last_checked_at
        row.last_check_error = model.last_check_error
