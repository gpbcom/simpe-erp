from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import ClassVar, Optional

# First-party imports
from models.settings.billing_settings import BillingSettings
from storage.mappers.base_mapper import BaseMapper
from storage.orm.billing.billing_settings_row import BillingSettingsRow


class BillingSettingsMapper(BaseMapper[BillingSettings, BillingSettingsRow]):
    """Converts between :class:`BillingSettings` and its row.

    Attributes:
        HAS_MODEL_TIMESTAMPS (ClassVar[bool]): ``False``. The model carries no
            ``created_at``, so the row's own creation time is the only one.

    Notes:
        - The model's ``updated_at`` is the row's, not a separate field: "when the
          invoicing rules last changed" and "when the row last changed" are the
          same event, and keeping two would let them disagree.
        - There is no ``created_at`` on the model, because nobody created these
          rules — they were seeded from the configuration file. The row still
          carries one, so the timestamp machinery is told not to read the model
          for it.
    """

    HAS_MODEL_TIMESTAMPS: ClassVar[bool] = False

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(
            model_class=BillingSettings,
            row_class=BillingSettingsRow,
            logger=logger,
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_model(self, row: BillingSettingsRow) -> BillingSettings:
        """Build the settings from a row's columns.

        Args:
            row (BillingSettingsRow): The row to read.

        Returns:
            BillingSettings: The domain model.

        Raises:
            MTInvalidBillingSettingsException: If a stored value no longer
                satisfies the model's validators.
        """
        self.logger.debug(
            "Building the billing settings from row %s (%s, %d-day terms).",
            row.id,
            row.periodicity,
            row.payment_terms_days,
        )
        return BillingSettings(
            id=row.id,
            periodicity=row.periodicity,
            payment_terms_days=row.payment_terms_days,
            late_penalty_multiplier=row.late_penalty_multiplier,
            recovery_indemnity_eur=row.recovery_indemnity_eur,
            escompte_offered=row.escompte_offered,
            updated_by=row.updated_by,
            updated_at=self.timestamps.to_utc(row.updated_at),
        )

    def _apply_fields(self, row: BillingSettingsRow, model: BillingSettings) -> None:  # noqa: E501
        """Write the settings onto a row's columns.

        Args:
            row (BillingSettingsRow): The row to write to.
            model (BillingSettings): The model carrying the values.
        """
        self.logger.debug(
            "Applying billing settings to row %s: %s, %d-day terms.",
            row.id,
            model.periodicity.value,
            model.payment_terms_days,
        )
        row.periodicity = model.periodicity.value
        row.payment_terms_days = model.payment_terms_days
        row.late_penalty_multiplier = model.late_penalty_multiplier
        row.recovery_indemnity_eur = model.recovery_indemnity_eur
        row.escompte_offered = model.escompte_offered
        row.updated_by = model.updated_by
