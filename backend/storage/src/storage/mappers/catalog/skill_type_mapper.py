from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import Optional

# First-party imports
from models.catalog.skill_type import SkillType
from storage.mappers.base_mapper import BaseMapper
from storage.orm.catalog.skill_type_row import SkillTypeRow


class SkillTypeMapper(BaseMapper[SkillType, SkillTypeRow]):
    """Converts between :class:`SkillType` and ``skill_types``.

    Notes:
        A flat table with no children, so the two directions
        :class:`~storage.mappers.base_mapper.BaseMapper` requires are the whole
        mapper. It carries timestamps on both sides: an entry is created once
        and edited for years, and the screen that lists it shows when it last
        moved.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(
            model_class=SkillType,
            row_class=SkillTypeRow,
            logger=logger,
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_model(self, row: SkillTypeRow) -> SkillType:
        """Build a catalogue entry from its row.

        Args:
            row (SkillTypeRow): The row to read.

        Returns:
            SkillType: The domain model.

        Raises:
            MTInvalidSkillTypeException: If a stored value no longer satisfies
                the model's validators.
        """
        self.logger.debug(
            "Building a skill type from row %s (%s).",
            row.id,
            row.code,
        )
        return SkillType(
            id=row.id,
            code=row.code,
            label=row.label,
            description=row.description,
            is_active=row.is_active,
            created_at=self.timestamps.to_utc(row.created_at),
            updated_at=self.timestamps.to_utc(row.updated_at),
        )

    def _apply_fields(self, row: SkillTypeRow, model: SkillType) -> None:
        """Write a catalogue entry's fields onto a row.

        Args:
            row (SkillTypeRow): The row to write to.
            model (SkillType): The model carrying the values.

        Notes:
            ``code`` is written like any other column even though no edit
            payload can change it. The rule that it is immutable lives in the
            request model, not here — a mapper that silently refused to write
            one field would be a second, invisible place to look when a create
            appeared to lose it.
        """
        row.code = model.code
        row.label = model.label
        row.description = model.description
        row.is_active = model.is_active
        self.logger.info(
            "Stored skill type row %s (%s), active=%s.",
            row.id,
            row.code,
            row.is_active,
        )
