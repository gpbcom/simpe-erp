from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import Optional

# Third-party imports
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.settings.billing_settings import BillingSettings
from storage.mappers.billing.billing_settings_mapper import BillingSettingsMapper
from storage.orm.billing.billing_settings_row import BillingSettingsRow
from storage.repositories.base import BaseRepository


class BillingSettingsRepository(BaseRepository[BillingSettingsRow]):
    """Reads and writes the single row of invoicing rules.

    Attributes:
        mapper (BillingSettingsMapper): Converts between the row and the model.

    Notes:
        No ``create`` and no ``delete``, exactly as the planning rules have
        neither. The rules always exist — seeded from the configuration file on
        first read — because an invoice printed without payment terms is a
        non-conforming document, and a caller that has to handle "the settings
        are missing" will eventually handle it by guessing.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        super().__init__(
            session=session,
            row_class=BillingSettingsRow,
        )
        self.mapper = BillingSettingsMapper()

    ############################
    # Publicly Exposed Methods #
    ############################

    async def get(self) -> Optional[BillingSettings]:
        """Return the stored rules, if they have been seeded.

        Returns:
            Optional[BillingSettings]: The rules, or ``None`` before the first
            read seeds them.
        """
        self.logger.debug("Fetching the billing settings.")
        row = await self.session.get(BillingSettingsRow, BillingSettings.SINGLETON_ID)
        if row is None:
            self.logger.debug("The billing settings have not been seeded yet.")
            return None
        return self.mapper.to_model(row)

    async def seed(self, settings: BillingSettings) -> BillingSettings:
        """Write the initial rules, if nothing is stored yet.

        Args:
            settings (BillingSettings): The rules to seed from configuration.

        Returns:
            BillingSettings: The stored rules — the existing ones when another
            caller seeded them first.

        Notes:
            Re-reads before writing rather than assuming the caller checked.
            Two requests arriving together would otherwise both insert the same
            primary key, and the loser would fail on a constraint rather than
            simply finding the row already there.
        """
        existing = await self.get()
        if existing is not None:
            self.logger.debug("The billing settings were already seeded.")
            return existing
        self.logger.info(
            "Seeding the billing settings: %s, %d-day terms.",
            settings.periodicity.value,
            settings.payment_terms_days,
        )
        row = self.mapper.to_row(settings)
        self.session.add(row)
        await self.session.flush()
        return self.mapper.to_model(row)

    async def update(self, settings: BillingSettings) -> Optional[BillingSettings]:
        """Replace the stored rules.

        Args:
            settings (BillingSettings): The rules to store.

        Returns:
            Optional[BillingSettings]: The updated rules, or ``None`` when
            nothing is stored yet.

        Notes:
            Returns ``None`` rather than seeding. An update arriving before the
            first read is a caller that skipped a step, and quietly creating the
            row would hide the ordering mistake.
        """
        row = await self.session.get(BillingSettingsRow, BillingSettings.SINGLETON_ID)
        if row is None:
            self.logger.warning(
                "Cannot update the billing settings: they are not seeded."
            )
            return None
        self.logger.info(
            "Updating the billing settings to %s, %d-day terms, changed by %s.",
            settings.periodicity.value,
            settings.payment_terms_days,
            settings.updated_by,
        )
        self.mapper.apply_to_row(row, settings)
        await self.session.flush()
        return self.mapper.to_model(row)
