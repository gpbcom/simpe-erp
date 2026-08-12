from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import ClassVar, List, Optional, Sequence

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.geo.postal_address import PostalAddress
from models.planning.intervention import Intervention
from storage.mappers.base_mapper import BaseMapper
from storage.mappers.exceptions import MTInterventionMissingPlanningRun
from storage.orm.planning.intervention_row import InterventionRow
from storage.orm.catalog.intervention_type_row import InterventionTypeRow


class InterventionMapper(BaseMapper[Intervention, InterventionRow]):
    """Converts a visit and the catalog entry it sells to and from their rows.

    Attributes:
        HAS_ROW_TIMESTAMPS (ClassVar[bool]): ``False``; the visits table carries
            no timestamp column.
        HAS_MODEL_TIMESTAMPS (ClassVar[bool]): ``False``; the visit model
            carries no timestamp field.

    Notes:
        - Two pairs live here. The scheduled visit
          (:class:`~models.planning.intervention.Intervention`) is the pair this
          mapper *is*, mapped through the inherited machinery. The catalog entry
          it sells (:class:`~models.catalog.intervention_type.InterventionType`)
          is carried alongside it, behind the ``*_type_*`` methods.
        - The second pair cannot go through
          :class:`~storage.mappers.base_mapper.BaseMapper`'s generic methods: a
          mapper is generic over exactly one model and one row, and the two
          pairs disagree about timestamps — a catalog entry is dated on both
          sides, a visit on neither. So :meth:`to_type_row` and
          :meth:`apply_to_type_row` are written out, but they are written out
          *once*: both funnel through :meth:`_apply_type_fields`, which is the
          property that matters — a column added to the catalog cannot be stored
          on create and forgotten on update.
        - A visit is not independently dated. It exists only because a planning
          run produced it, is deleted with that run, and the run's own
          ``started_at`` is when it came into being — so neither the model nor
          the table carries ``created_at`` or ``updated_at``, and this mapper
          tells the base class not to stamp them.
        - The address is flattened onto columns rather than stored as a blob:
          an assistant's round is read back by day, coordinates included.
    """

    HAS_ROW_TIMESTAMPS: ClassVar[bool] = False
    HAS_MODEL_TIMESTAMPS: ClassVar[bool] = False

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(
            model_class=Intervention,
            row_class=InterventionRow,
            logger=logger,
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_model(self, row: InterventionRow) -> Intervention:
        """Build a visit from a row's columns.

        Args:
            row (InterventionRow): The row to read.

        Returns:
            Intervention: The domain model.

        Raises:
            MTInterventionInvalidAddress: If a stored address value no longer
                satisfies the model's validators.

        Notes:
            Rebuilding the address issues no geocoding request. A visit only
            exists because its customer had a resolved coordinate — the
            requirement builder drops the ones that did not — so the address
            always comes back already resolved, which
            :class:`~models.geo.postal_address.PostalAddress` treats as nothing
            to look up. That matters here more than anywhere: a planning page
            loads dozens of visits at once.
        """
        self.logger.debug(
            "Building an intervention from row %s (day %s, hca %s).",
            row.id,
            row.day,
            row.hca_id,
        )
        address = PostalAddress(
            street=row.street,
            postal_code=row.postal_code,
            city=row.city,
            country=row.country,
            latitude=row.latitude,
            longitude=row.longitude,
            geocoding_error=row.geocoding_error,
        )
        return Intervention(
            id=row.id,
            planning_run_id=row.planning_run_id,
            company_id=row.company_id,
            team_id=row.team_id,
            name=row.name,
            intervention_type_id=row.intervention_type_id,
            quote_line_id=row.quote_line_id,
            hca_id=row.hca_id,
            hca_full_name=row.hca_full_name,
            customer_id=row.customer_id,
            day=row.day,
            start_time=row.start_time,
            end_time=row.end_time,
            address=address,
            status=row.status,
        )

    def _apply_fields(self, row: InterventionRow, model: Intervention) -> None:
        """Write a visit's fields onto a row.

        Args:
            row (InterventionRow): The row to write to.
            model (Intervention): The model carrying the values.

        Raises:
            MTInterventionMissingPlanningRun: If the visit names no planning
                run, which would leave it unattached to anything that produced
                it.
        """
        if model.planning_run_id is None:
            self.logger.error(
                "Intervention row %s names no planning run: refusing to store "
                "a visit nothing produced.",
                row.id,
            )
            raise MTInterventionMissingPlanningRun(
                "An intervention must name the planning run that produced it."
            )
        self.logger.debug(
            "Applying an intervention onto row %s (day %s, hca %s).",
            row.id,
            model.day,
            model.hca_id,
        )
        row.planning_run_id = model.planning_run_id
        row.company_id = model.company_id
        row.team_id = model.team_id
        row.name = model.name
        row.intervention_type_id = model.intervention_type_id
        row.quote_line_id = model.quote_line_id
        row.hca_id = model.hca_id
        row.hca_full_name = model.hca_full_name
        row.customer_id = model.customer_id
        row.day = model.day
        row.start_time = model.start_time
        row.end_time = model.end_time
        row.street = model.address.street
        row.postal_code = model.address.postal_code
        row.city = model.address.city
        row.country = model.address.country
        row.latitude = model.address.latitude
        row.longitude = model.address.longitude
        row.geocoding_error = model.address.geocoding_error
        row.status = model.status.value
        if model.address.geocoding_error:
            self.logger.warning(
                "Storing intervention row %s with a geocoding error (%s): the "
                "round cannot be routed through it.",
                row.id,
                model.address.geocoding_error,
            )

    def _build_type_model(self, row: InterventionTypeRow) -> InterventionType:
        """Build a catalog entry from a row's columns.

        Args:
            row (InterventionTypeRow): The row to read.

        Returns:
            InterventionType: The domain model.

        Raises:
            MTInvalidInterventionTypeException: If a stored value no longer
                satisfies the model's validators.
        """
        self.logger.debug(
            "Building an intervention type from row %s (active %s).",
            row.id,
            row.is_active,
        )
        return InterventionType(
            id=row.id,
            name=row.name,
            code=row.code,
            description=row.description,
            service_category=row.service_category,
            base_hourly_rate_ht=row.base_hourly_rate_ht,
            is_active=row.is_active,
            required_certification_codes=list(row.required_certification_codes or []),
            required_skill_codes=list(row.required_skill_codes or []),
            created_at=self.timestamps.to_utc(row.created_at),
            updated_at=self.timestamps.to_utc(row.updated_at),
        )

    def _apply_type_fields(
        self, row: InterventionTypeRow, model: InterventionType
    ) -> None:
        """Write a catalog entry's fields onto a row.

        Args:
            row (InterventionTypeRow): The row to write to, carrying its
                identifier.
            model (InterventionType): The model carrying the values.

        Notes:
            Called on both the insert and the update path, so it sets every
            column the catalog owns. ``id``, ``created_at`` and ``updated_at``
            are handled by the two methods that call it.
        """
        self.logger.debug(
            "Applying an intervention type onto row %s (active %s).",
            row.id,
            model.is_active,
        )
        row.name = model.name
        row.code = model.code
        row.description = model.description
        row.service_category = model.service_category.value
        row.base_hourly_rate_ht = model.base_hourly_rate_ht
        row.is_active = model.is_active
        # A new list, not the model's own: the JSON column is mutable, and
        # sharing the object would let a later edit to the model reach a row
        # SQLAlchemy has already decided is clean.
        row.required_certification_codes = list(model.required_certification_codes)
        row.required_skill_codes = list(model.required_skill_codes)
        if not model.is_active:
            self.logger.info(
                "Intervention type row %s is stored as inactive: it can no "
                "longer be quoted.",
                row.id,
            )

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_type_model(self, row: InterventionTypeRow) -> InterventionType:
        """Convert a catalog row into a domain model.

        Args:
            row (InterventionTypeRow): The row to convert.

        Returns:
            InterventionType: The domain model.

        Raises:
            Exception: Whatever the model raises when a stored value no longer
                satisfies its validators. The catch is broad and re-raises
                untouched: it exists only to log which row failed, and naming a
                single exception family here would let a nested value's own
                failure through unlogged.
        """
        self.logger.debug(
            "Mapping %s row %s into an %s.",
            InterventionTypeRow.__tablename__,
            row.id,
            InterventionType.__name__,
        )
        try:
            model = self._build_type_model(row)
        except Exception as exc:
            self.logger.error(
                "Error mapping %s row %s into an %s: %s.",
                InterventionTypeRow.__tablename__,
                row.id,
                InterventionType.__name__,
                exc,
            )
            raise
        return model

    def to_type_models(
        self, rows: Sequence[InterventionTypeRow]
    ) -> List[InterventionType]:
        """Convert several catalog rows into domain models.

        Args:
            rows (Sequence[InterventionTypeRow]): The rows to convert.

        Returns:
            List[InterventionType]: The domain models, in the order given.

        Raises:
            Exception: The model's own validation exception family, if any row
                fails to convert.

        Notes:
            One bad row fails the whole page rather than being skipped. A
            catalog silently one entry short is a far harder bug to notice than
            a failed request, and a quote priced from it is wrong in a way
            nobody would question.
        """
        if not rows:
            self.logger.debug("No %s row to map.", InterventionTypeRow.__tablename__)
            return []
        models = [self.to_type_model(row) for row in rows]
        self.logger.info(
            "Mapped %d %s row(s) into %s models.",
            len(models),
            InterventionTypeRow.__tablename__,
            InterventionType.__name__,
        )
        return models

    def to_type_row(self, model: InterventionType) -> InterventionTypeRow:
        """Convert a catalog entry into a new database row.

        Args:
            model (InterventionType): The model to convert.

        Returns:
            InterventionTypeRow: A row ready to be added to a session.

        Notes:
            Unlike a visit, a catalog entry is dated on both sides: it is
            created once and edited for years, and the screen that lists it
            shows when it last moved.
        """
        now = self._utc_now()
        row_id = self._resolve_row_id(model)
        self.logger.debug(
            "Mapping an %s model into %s row %s.",
            InterventionType.__name__,
            InterventionTypeRow.__tablename__,
            row_id,
        )
        row = InterventionTypeRow(id=row_id)
        row.created_at = model.created_at if model.created_at else now
        row.updated_at = now
        self._apply_type_fields(row, model)
        self.logger.info(
            "Built %s row %s from an %s model.",
            InterventionTypeRow.__tablename__,
            row_id,
            InterventionType.__name__,
        )
        return row

    def apply_to_type_row(
        self, row: InterventionTypeRow, model: InterventionType
    ) -> InterventionTypeRow:
        """Copy a catalog entry's fields onto an existing row.

        Args:
            row (InterventionTypeRow): The row to update in place.
            model (InterventionType): The model carrying the new values.

        Returns:
            InterventionTypeRow: The same row, mutated.

        Notes:
            ``created_at`` is never touched: the row's own creation time is the
            truth, not whatever the caller happened to send back. A payload
            naming a different identifier is logged at ``WARNING`` and then
            ignored — the row being written is the one the repository loaded.
        """
        self.logger.debug(
            "Applying an %s model onto %s row %s.",
            InterventionType.__name__,
            InterventionTypeRow.__tablename__,
            row.id,
        )
        if model.id and str(model.id) != row.id:
            self.logger.warning(
                "Ignoring %s identifier %s: %s row %s is the one being updated.",
                InterventionType.__name__,
                model.id,
                InterventionTypeRow.__tablename__,
                row.id,
            )
        self._apply_type_fields(row, model)
        row.updated_at = self._utc_now()
        self.logger.info(
            "Applied an %s model onto %s row %s.",
            InterventionType.__name__,
            InterventionTypeRow.__tablename__,
            row.id,
        )
        return row
