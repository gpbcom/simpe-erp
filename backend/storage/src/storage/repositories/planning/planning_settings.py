from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import Optional

# Third-party imports
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.settings.planning_settings import PlanningSettings
from storage.mappers.planning.planning_settings_mapper import PlanningSettingsMapper
from storage.orm.planning.planning_settings_row import PlanningSettingsRow
from storage.repositories.base import BaseRepository


class PlanningSettingsRepository(BaseRepository[PlanningSettingsRow]):
    """Reads and writes the single row of planning rules.

    Attributes:
        mapper (PlanningSettingsMapper): Converts between the row and the model.

    Notes:
        No ``create`` and no ``delete``. The rules always exist — seeded from
        the configuration file on first read — because a planner with no rules
        has nothing sensible to fall back on, and a caller that has to handle
        "the settings are missing" will eventually handle it by guessing.
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
            row_class=PlanningSettingsRow,
        )
        self.mapper = PlanningSettingsMapper()

    ############################
    # Publicly Exposed Methods #
    ############################

    async def get(self) -> Optional[PlanningSettings]:
        """Return the stored rules, if they have been seeded.

        Returns:
            Optional[PlanningSettings]: The rules, or ``None`` before the first
            read seeds them.
        """
        self.logger.debug("Fetching the planning settings.")
        row = await self.session.get(PlanningSettingsRow, PlanningSettings.SINGLETON_ID)
        if row is None:
            self.logger.debug("The planning settings have not been seeded yet.")
            return None
        return self.mapper.to_model(row)

    async def seed(self, settings: PlanningSettings) -> PlanningSettings:
        """Write the initial rules, if nothing is stored yet.

        Args:
            settings (PlanningSettings): The rules to seed from configuration.

        Returns:
            PlanningSettings: The stored rules — the existing ones when another
            caller seeded them first.

        Notes:
            Re-reads before writing rather than assuming the caller checked.
            Two requests arriving together would otherwise both insert the same
            primary key, and the loser would fail on a constraint rather than
            simply finding the row already there.
        """
        existing = await self.get()
        if existing is not None:
            self.logger.debug("The planning settings were already seeded.")
            return existing
        self.logger.info(
            "Seeding the planning settings: radius %.1f km, lunch %d min.",
            settings.max_intervention_radius_km,
            settings.lunch_break_minutes,
        )
        row = self.mapper.to_row(settings)
        self.session.add(row)
        await self.session.flush()
        return self.mapper.to_model(row)

    async def update(self, settings: PlanningSettings) -> Optional[PlanningSettings]:
        """Replace the stored rules.

        Args:
            settings (PlanningSettings): The rules to store.

        Returns:
            Optional[PlanningSettings]: The updated rules, or ``None`` when
            nothing is stored yet.

        Notes:
            Returns ``None`` rather than seeding. An update arriving before the
            first read is a caller that skipped a step, and quietly creating
            the row would hide the ordering mistake.
        """
        row = await self.session.get(PlanningSettingsRow, PlanningSettings.SINGLETON_ID)
        if row is None:
            self.logger.warning(
                "Cannot update the planning settings: they are not seeded."
            )
            return None
        self.logger.info(
            "Updating the planning settings to radius %.1f km, lunch %d min, "
            "changed by %s.",
            settings.max_intervention_radius_km,
            settings.lunch_break_minutes,
            settings.updated_by,
        )
        self.mapper.apply_to_row(row, settings)
        await self.session.flush()
        return self.mapper.to_model(row)
