from __future__ import annotations

# Standard library imports
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import ClassVar, Generic, List, Optional, Sequence, Type, TypeVar
from uuid import uuid4

# Third-party imports
from pydantic import BaseModel

# First-party imports
from storage.mappers.timestamp_normalizer import TimestampNormalizer
from storage.orm.base import Base

ModelType = TypeVar("ModelType", bound=BaseModel)
RowType = TypeVar("RowType", bound=Base)


class BaseMapper(ABC, Generic[ModelType, RowType]):
    """Shared conversion machinery between a domain model and its ORM row.

    Attributes:
        HAS_ROW_TIMESTAMPS (ClassVar[bool]): Whether the table carries
            ``created_at`` and ``updated_at`` columns for this class to stamp.
        HAS_MODEL_TIMESTAMPS (ClassVar[bool]): Whether the domain model carries
            a ``created_at`` this class may preserve when building a row.
        model_class (Type[ModelType]): The domain model this mapper builds.
        row_class (Type[RowType]): The table this mapper writes.
        timestamps (TimestampNormalizer): Normalizes stored timestamps to
            timezone-aware UTC.
        logger (Logger): Logger for mapping operations.

    Notes:
        - A subclass supplies only the two directions that genuinely differ per
          table: :meth:`_build_model` reads a row, :meth:`_apply_fields` writes
          one. Everything the mappers used to repeat — generating an
          identifier, stamping the clock, normalizing timestamps, logging,
          reporting a validation failure — lives here once, so no subclass
          declares :meth:`to_model`, :meth:`to_models`, :meth:`to_row` or
          :meth:`apply_to_row` itself.
        - Insert and update share :meth:`_apply_fields`. Building a fresh row
          used to be a second, independent copy of the same column list, which
          is exactly the kind of duplication that lets an added field be
          written on create and silently forgotten on update.
        - ``created_at`` is only ever set when the row is built. The update path
          never touches it. The row's own creation time is the truth, not
          whatever the caller happened to send back.
        - Every model mapped here exposes ``id``. That is the contract a
          persisted model owes this class, and it is not expressible through the
          ``BaseModel`` bound. The two timestamps are *not* part of it: a
          planning run and the visits it produced are dated by the run itself,
          and a quote's model deliberately leaves them to the table. The two
          class flags say which of the two sides carries them, so a mapper for a
          table without them inherits everything else rather than being written
          out by hand.
    """

    HAS_ROW_TIMESTAMPS: ClassVar[bool] = True
    HAS_MODEL_TIMESTAMPS: ClassVar[bool] = True

    def __init__(
        self,
        model_class: Type[ModelType],
        row_class: Type[RowType],
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the mapper.

        Args:
            model_class (Type[ModelType]): The domain model this mapper builds.
            row_class (Type[RowType]): The table this mapper writes.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.model_class = model_class
        self.row_class = row_class
        self.timestamps = TimestampNormalizer()
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug(
            "%s created for %s <-> %s.",
            type(self).__name__,
            model_class.__name__,
            row_class.__tablename__,
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _utc_now(self) -> datetime:
        """Return the current instant as timezone-aware UTC.

        Returns:
            datetime: The current instant in UTC.

        Notes:
            The clock is read here rather than in the domain model, which keeps
            the models free of ambient state and makes them trivially testable.
        """
        return datetime.now(UTC)

    def _resolve_row_id(self, model: ModelType) -> str:
        """Return the identifier a new row should carry.

        Args:
            model (ModelType): The model being stored.

        Returns:
            str: The model's identifier, or a freshly minted UUID when it
            carries none.

        Notes:
            - A caller never has to mint an identifier, so a create path can
              hand over a model straight from a request payload.
            - The log names the model it was handed rather than the one the
              mapper was built for. The two are the same everywhere but in
              :class:`~storage.mappers.planning.intervention_mapper.InterventionMapper`,
              which carries a second pair alongside its own and reuses this.
        """
        if model.id:
            self.logger.debug(
                "Reusing %s identifier %s supplied by the caller.",
                type(model).__name__,
                model.id,
            )
            return str(model.id)
        row_id = str(uuid4())
        self.logger.debug("Generated %s identifier %s.", type(model).__name__, row_id)
        return row_id

    def _stamp_new_row(self, row: RowType, model: ModelType, now: datetime) -> None:
        """Write the creation and update timestamps onto a freshly built row.

        Args:
            row (RowType): The row being built, carrying its identifier.
            model (ModelType): The model being stored.
            now (datetime): The instant the row is being built.

        Notes:
            A table without the two columns is left alone rather than raising:
            an intervention and a planning run are dated by the run's own
            ``started_at``, and stamping them would mean a migration to add
            columns nothing reads.
        """
        if not self.HAS_ROW_TIMESTAMPS:
            self.logger.debug(
                "%s carries no timestamp column: none stamped on row %s.",
                self.row_class.__tablename__,
                row.id,
            )
            return
        created_at = model.created_at if self.HAS_MODEL_TIMESTAMPS else None
        row.created_at = created_at if created_at else now
        row.updated_at = now

    @abstractmethod
    def _build_model(self, row: RowType) -> ModelType:
        """Build the domain model from a row's columns.

        Args:
            row (RowType): The row to read, with any children loaded.

        Returns:
            ModelType: The domain model.

        Raises:
            Exception: The model's own validation exception family, when a
                stored value no longer satisfies its validators.
        """

    @abstractmethod
    def _apply_fields(self, row: RowType, model: ModelType) -> None:
        """Write a model's fields onto a row's columns.

        Args:
            row (RowType): The row to write to, carrying its identifier.
            model (ModelType): The model carrying the values.

        Notes:
            Called on both the insert and the update path, so an implementation
            must set every column it owns rather than assuming a pristine row —
            a value cleared on the model has to be cleared on the row too.
            ``id``, ``created_at`` and ``updated_at`` are owned by this class
            and must not be touched here.
        """

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_model(self, row: RowType) -> ModelType:
        """Convert a database row into a domain model.

        Args:
            row (RowType): The row to convert, with any children loaded.

        Returns:
            ModelType: The domain model.

        Raises:
            Exception: Whatever the model raises when a stored value no longer
                satisfies its validators — its own exception family, a nested
                model's, or :class:`~pydantic.ValidationError`.

        Notes:
            - Validation is deliberately re-run on read. A row written by an
              older schema, or edited by hand, is caught here rather than
              propagating a malformed model into the rest of the application.
            - The catch is deliberately broad, and re-raises untouched: it
              exists only to log which row failed. A nested value fails with its
              own exception family — a bad postcode raises
              ``MTInvalidPostalAddressException``, not the owning model's — so
              naming a single family here would let exactly the hardest failures
              through unlogged.
        """
        self.logger.debug(
            "Mapping %s row %s into a %s.",
            self.row_class.__tablename__,
            row.id,
            self.model_class.__name__,
        )
        try:
            model = self._build_model(row)
        except Exception as exc:
            self.logger.error(
                "Error mapping %s row %s into a %s: %s.",
                self.row_class.__tablename__,
                row.id,
                self.model_class.__name__,
                exc,
            )
            raise
        self.logger.debug(
            "Mapped %s row %s into a %s.",
            self.row_class.__tablename__,
            row.id,
            self.model_class.__name__,
        )
        return model

    def to_models(self, rows: Sequence[RowType]) -> List[ModelType]:
        """Convert several database rows into domain models.

        Args:
            rows (Sequence[RowType]): The rows to convert.

        Returns:
            List[ModelType]: The domain models, in the order given.

        Raises:
            Exception: The model's own validation exception family, if any row
                fails to convert.

        Notes:
            One bad row fails the whole page rather than being skipped. A list
            silently one item short is a far harder bug to notice than a failed
            request, and a planning built from a truncated roster is wrong in a
            way nobody would question.
        """
        self.logger.debug(
            "Mapping %d %s row(s) into %s models.",
            len(rows),
            self.row_class.__tablename__,
            self.model_class.__name__,
        )
        if not rows:
            self.logger.debug("No %s row to map.", self.row_class.__tablename__)
            return []
        models = [self.to_model(row) for row in rows]
        self.logger.info(
            "Mapped %d %s row(s) into %s models.",
            len(models),
            self.row_class.__tablename__,
            self.model_class.__name__,
        )
        return models

    def to_row(self, model: ModelType) -> RowType:
        """Convert a domain model into a new database row.

        Args:
            model (ModelType): The model to convert.

        Returns:
            RowType: A row ready to be added to a session.

        Notes:
            The row is created with its identifier, stamped, then filled
            through the same :meth:`_apply_fields` the update path uses, so the
            two can never drift apart.
        """
        now = self._utc_now()
        row_id = self._resolve_row_id(model)
        self.logger.debug(
            "Mapping a %s model into %s row %s.",
            self.model_class.__name__,
            self.row_class.__tablename__,
            row_id,
        )
        row = self.row_class(id=row_id)
        self._stamp_new_row(row, model, now)
        self._apply_fields(row, model)
        self.logger.info(
            "Built %s row %s from a %s model.",
            self.row_class.__tablename__,
            row_id,
            self.model_class.__name__,
        )
        return row

    def apply_to_row(self, row: RowType, model: ModelType) -> RowType:
        """Copy a model's fields onto an existing row.

        Args:
            row (RowType): The row to update in place.
            model (ModelType): The model carrying the new values.

        Returns:
            RowType: The same row, mutated.

        Notes:
            Used for updates rather than building a fresh row, so the session
            issues an ``UPDATE`` instead of trying to insert a duplicate key.
            A payload naming a different identifier is logged at ``WARNING`` and
            then ignored: the row being written is the one the repository
            loaded, and letting a body rename a record would be a way to edit a
            neighbour's data.
        """
        self.logger.debug(
            "Applying a %s model onto %s row %s.",
            self.model_class.__name__,
            self.row_class.__tablename__,
            row.id,
        )
        if model.id and str(model.id) != row.id:
            self.logger.warning(
                "Ignoring %s identifier %s: %s row %s is the one being updated.",
                self.model_class.__name__,
                model.id,
                self.row_class.__tablename__,
                row.id,
            )
        self._apply_fields(row, model)
        if self.HAS_ROW_TIMESTAMPS:
            row.updated_at = self._utc_now()
        self.logger.info(
            "Applied a %s model onto %s row %s.",
            self.model_class.__name__,
            self.row_class.__tablename__,
            row.id,
        )
        return row
