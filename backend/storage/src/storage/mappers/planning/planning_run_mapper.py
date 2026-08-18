from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import ClassVar, List, Optional

# First-party imports
from models.planning.planning_run import PlanningRun
from storage.mappers.base_mapper import BaseMapper
from storage.orm.planning.planning_run_row import PlanningRunRow


class PlanningRunMapper(BaseMapper[PlanningRun, PlanningRunRow]):
    """Converts between :class:`PlanningRun` and its row.

    Attributes:
        ID_SEPARATOR (ClassVar[str]): Delimiter joining the unassigned ids.
        HAS_ROW_TIMESTAMPS (ClassVar[bool]): ``False``. The table carries no
            timestamp column.
        HAS_MODEL_TIMESTAMPS (ClassVar[bool]): ``False``. The model carries no
            timestamp field.

    Notes:
        - A run dates itself. ``started_at`` and ``finished_at`` are the record
          of when the solver ran, and they are written by the caller rather than
          stamped by this layer, so neither side carries the generic
          ``created_at``/``updated_at`` pair.
        - Insert and update share :meth:`_apply_fields`, so the period and the
          requester are rewritten on every save. They never change in practice —
          the model being saved is the one that was read — and writing them is
          what stops a field added later from being stored on create and quietly
          forgotten on update.
    """

    ID_SEPARATOR: ClassVar[str] = ","
    HAS_ROW_TIMESTAMPS: ClassVar[bool] = False
    HAS_MODEL_TIMESTAMPS: ClassVar[bool] = False

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(
            model_class=PlanningRun,
            row_class=PlanningRunRow,
            logger=logger,
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _join_ids(self, identifiers: List[str]) -> Optional[str]:
        """Flatten the unassigned identifiers into one column.

        Args:
            identifiers (List[str]): The identifiers to store.

        Returns:
            Optional[str]: The delimited string, or ``None`` when empty.

        Notes:
            An empty list stores as ``NULL`` rather than an empty string, so
            "nothing was left over" and "the column was never written" read the
            same way back.
        """
        return self.ID_SEPARATOR.join(identifiers) if identifiers else None

    def _split_ids(self, stored: Optional[str]) -> List[str]:
        """Rebuild the unassigned identifiers from their column.

        Args:
            stored (Optional[str]): The delimited string, or ``None``.

        Returns:
            List[str]: The identifiers, empty when nothing was stored.
        """
        if not stored:
            return []
        return [part for part in stored.split(self.ID_SEPARATOR) if part]

    def _build_model(self, row: PlanningRunRow) -> PlanningRun:
        """Build a run from a row's columns.

        Args:
            row (PlanningRunRow): The row to read.

        Returns:
            PlanningRun: The domain model.

        Raises:
            MTPlanningRunInvalidStatus: If a stored value no longer satisfies
                the model's validators.
        """
        self.logger.debug(
            "Building a planning run from row %s (status %s).",
            row.id,
            row.status,
        )
        return PlanningRun(
            id=row.id,
            status=row.status,
            company_id=row.company_id,
            team_id=row.team_id,
            requested_by=row.requested_by,
            period_start=row.period_start,
            period_end=row.period_end,
            started_at=self.timestamps.to_utc(row.started_at),
            finished_at=self.timestamps.to_utc(row.finished_at),
            total_travel_minutes=row.total_travel_minutes,
            scheduled_count=row.scheduled_count,
            is_optimised=row.is_optimised,
            unassigned_requirement_ids=self._split_ids(row.unassigned_requirement_ids),
            unplaced_quotes=row.unplaced_quotes or [],
            error_message=row.error_message,
        )

    def _apply_fields(self, row: PlanningRunRow, model: PlanningRun) -> None:
        """Write a run's fields onto a row.

        Args:
            row (PlanningRunRow): The row to write to.
            model (PlanningRun): The model carrying the values.
        """
        self.logger.debug(
            "Applying a planning run onto row %s (status %s).",
            row.id,
            model.status.value,
        )
        row.status = model.status.value
        row.company_id = model.company_id
        row.team_id = model.team_id
        row.requested_by = model.requested_by
        row.period_start = model.period_start
        row.period_end = model.period_end
        row.started_at = model.started_at
        row.finished_at = model.finished_at
        row.total_travel_minutes = model.total_travel_minutes
        row.scheduled_count = model.scheduled_count
        row.is_optimised = model.is_optimised
        row.unassigned_requirement_ids = self._join_ids(
            model.unassigned_requirement_ids
        )
        row.unplaced_quotes = [
            entry.model_dump(mode="json") for entry in model.unplaced_quotes
        ]
        row.error_message = model.error_message
        if model.unassigned_requirement_ids:
            self.logger.warning(
                "Planning run row %s is stored with %d unplaced requirement(s).",
                row.id,
                len(model.unassigned_requirement_ids),
            )
