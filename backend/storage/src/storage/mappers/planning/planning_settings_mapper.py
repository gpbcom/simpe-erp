from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import ClassVar, Optional

# First-party imports
from models.settings.planning_settings import PlanningSettings
from storage.mappers.base_mapper import BaseMapper
from storage.orm.planning.planning_settings_row import PlanningSettingsRow


class PlanningSettingsMapper(BaseMapper[PlanningSettings, PlanningSettingsRow]):
    """Converts between :class:`PlanningSettings` and its row.

    Attributes:
        HAS_MODEL_TIMESTAMPS (ClassVar[bool]): ``False``. The model carries no
            ``created_at``, so the row's own creation time is the only one.

    Notes:
        The model's ``updated_at`` is the row's, not a separate field: "when
        the rules last changed" and "when the row last changed" are the same
        event here, and keeping two would let them disagree.

        There is no ``created_at`` on the model, because nobody created these
        rules — they were seeded. The row still carries one, so the timestamp
        machinery is told not to read the model for it.
    """

    HAS_MODEL_TIMESTAMPS: ClassVar[bool] = False

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(
            model_class=PlanningSettings,
            row_class=PlanningSettingsRow,
            logger=logger,
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_model(self, row: PlanningSettingsRow) -> PlanningSettings:
        """Build the settings from a row's columns.

        Args:
            row (PlanningSettingsRow): The row to read.

        Returns:
            PlanningSettings: The domain model.

        Raises:
            MTInvalidPlanningSettingsException: If a stored value no longer
                satisfies the model's validators.
        """
        self.logger.debug(
            "Building the planning settings from row %s (radius %.1f km).",
            row.id,
            row.max_intervention_radius_km,
        )
        return PlanningSettings(
            id=row.id,
            max_intervention_radius_km=row.max_intervention_radius_km,
            day_start_minute=row.day_start_minute,
            day_end_minute=row.day_end_minute,
            lunch_break_minutes=row.lunch_break_minutes,
            lunch_window_start_minute=row.lunch_window_start_minute,
            lunch_window_end_minute=row.lunch_window_end_minute,
            updated_by=row.updated_by,
            updated_at=self.timestamps.to_utc(row.updated_at),
        )

    def _apply_fields(self, row: PlanningSettingsRow, model: PlanningSettings) -> None:
        """Write the settings onto a row's columns.

        Args:
            row (PlanningSettingsRow): The row to write to.
            model (PlanningSettings): The model carrying the values.
        """
        self.logger.debug(
            "Applying planning settings to row %s: radius %.1f km, lunch %d min.",
            row.id,
            model.max_intervention_radius_km,
            model.lunch_break_minutes,
        )
        row.max_intervention_radius_km = model.max_intervention_radius_km
        row.day_start_minute = model.day_start_minute
        row.day_end_minute = model.day_end_minute
        row.lunch_break_minutes = model.lunch_break_minutes
        row.lunch_window_start_minute = model.lunch_window_start_minute
        row.lunch_window_end_minute = model.lunch_window_end_minute
        row.updated_by = model.updated_by
