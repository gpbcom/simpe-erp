from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import ClassVar, List, Optional
from uuid import uuid4

# First-party imports
from models.planning.planning_run.unplaced_quote import UnplacedQuote
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from models.quoting.quote_type_week_aggregate import QuoteTypeWeekAggregate
from storage.mappers.base_mapper import BaseMapper
from storage.orm.quoting.quote_aggregate_row import QuoteAggregateRow
from storage.orm.quoting.quote_line_row import QuoteLineRow
from storage.orm.quoting.quote_row import QuoteRow


class QuoteMapper(BaseMapper[Quote, QuoteRow]):
    """Converts between :class:`Quote` and its three tables.

    Attributes:
        HAS_MODEL_TIMESTAMPS (ClassVar[bool]): ``False``; the model carries no
            timestamp field, so the table's own clock is the only one.

    Notes:
        - A quote is one aggregate spread over three tables — the header, its
          lines and its per-week totals — and all three are written and read
          together. Splitting the mapping would let a caller save a header
          without its lines, which is a quote that prints as blank.
        - Line order is carried by an explicit ``position`` column rather than
          left to the database. A quote is a document: the order the operator
          typed the services in is what the customer reads.
        - The table is stamped but the model is not: nothing above this layer
          asks when a quote was written, only when it was issued and until when
          it stands, which are dates the operator chooses.
    """

    HAS_MODEL_TIMESTAMPS: ClassVar[bool] = False

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(model_class=Quote, row_class=QuoteRow, logger=logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _line_to_model(self, row: QuoteLineRow) -> QuoteLine:
        """Rebuild a quote line from its row.

        Args:
            row (QuoteLineRow): The row to read.

        Returns:
            QuoteLine: The domain model.
        """
        return QuoteLine(
            id=row.id,
            name=row.name,
            intervention_type_id=row.intervention_type_id,
            service_category=row.service_category,
            service_date=row.service_date,
            earliest_start=row.earliest_start,
            latest_end=row.latest_end,
            duration_minutes=row.duration_minutes,
            hourly_rate_ht=row.hourly_rate_ht,
            total_ht=row.total_ht,
            vat_amount=row.vat_amount,
            total_ttc=row.total_ttc,
            # None and [] mean different things — inherit the catalog, against
            # require nothing — so the column is passed straight through rather
            # than defaulted.
            required_certification_codes=(
                list(row.required_certification_codes)
                if row.required_certification_codes is not None
                else None
            ),
            required_skill_codes=(
                list(row.required_skill_codes)
                if row.required_skill_codes is not None
                else None
            ),
        )

    def _aggregate_to_model(self, row: QuoteAggregateRow) -> QuoteTypeWeekAggregate:
        """Rebuild a weekly aggregate from its row.

        Args:
            row (QuoteAggregateRow): The row to read.

        Returns:
            QuoteTypeWeekAggregate: The domain model.
        """
        return QuoteTypeWeekAggregate(
            intervention_type_id=row.intervention_type_id,
            intervention_type_name=row.intervention_type_name,
            iso_year=row.iso_year,
            iso_week=row.iso_week,
            week_start_date=row.week_start_date,
            line_count=row.line_count,
            total_minutes=row.total_minutes,
            total_ht=row.total_ht,
            vat_amount=row.vat_amount,
            total_ttc=row.total_ttc,
        )

    def _line_rows(self, quote_id: str, lines: List[QuoteLine]) -> List[QuoteLineRow]:
        """Build the line rows for a quote.

        Args:
            quote_id (str): The owning quote's identifier.
            lines (List[QuoteLine]): The lines to store.

        Returns:
            List[QuoteLineRow]: Rows carrying their display position.

        Notes:
            A line's own identifier is kept when it has one, so re-pricing a
            quote does not renumber lines a customer has already seen.
        """
        return [
            QuoteLineRow(
                id=line.id if line.id else str(uuid4()),
                quote_id=quote_id,
                position=position,
                name=line.name,
                intervention_type_id=line.intervention_type_id,
                service_category=line.service_category.value,
                service_date=line.service_date,
                earliest_start=line.earliest_start,
                latest_end=line.latest_end,
                duration_minutes=line.duration_minutes,
                hourly_rate_ht=line.hourly_rate_ht,
                total_ht=line.total_ht,
                vat_amount=line.vat_amount,
                total_ttc=line.total_ttc,
                required_certification_codes=(
                    list(line.required_certification_codes)
                    if line.required_certification_codes is not None
                    else None
                ),
                required_skill_codes=(
                    list(line.required_skill_codes)
                    if line.required_skill_codes is not None
                    else None
                ),
            )
            for position, line in enumerate(lines)
        ]

    def _aggregate_rows(
        self, quote_id: str, aggregates: List[QuoteTypeWeekAggregate]
    ) -> List[QuoteAggregateRow]:
        """Build the aggregate rows for a quote.

        Args:
            quote_id (str): The owning quote's identifier.
            aggregates (List[QuoteTypeWeekAggregate]): The totals to store.

        Returns:
            List[QuoteAggregateRow]: Freshly built rows.

        Notes:
            Always given a new identifier: an aggregate is a derived figure
            recomputed on every pricing run, not a record anything refers to.
        """
        return [
            QuoteAggregateRow(
                id=str(uuid4()),
                quote_id=quote_id,
                intervention_type_id=entry.intervention_type_id,
                intervention_type_name=entry.intervention_type_name,
                iso_year=entry.iso_year,
                iso_week=entry.iso_week,
                week_start_date=entry.week_start_date,
                line_count=entry.line_count,
                total_minutes=entry.total_minutes,
                total_ht=entry.total_ht,
                vat_amount=entry.vat_amount,
                total_ttc=entry.total_ttc,
            )
            for entry in aggregates
        ]

    def _build_model(self, row: QuoteRow) -> Quote:
        """Build a quote from a row's columns and children.

        Args:
            row (QuoteRow): The row to read, with its children loaded.

        Returns:
            Quote: The domain model.

        Raises:
            MTInvalidQuoteException: If a stored value no longer satisfies the
                model's validators.
        """
        self.logger.debug(
            "Building a quote from row %s (%d line(s), status %s).",
            row.id,
            len(row.lines),
            row.status,
        )
        return Quote(
            id=row.id,
            company_id=row.company_id,
            reference=row.reference,
            customer_id=row.customer_id,
            status=row.status,
            lines=[self._line_to_model(line) for line in row.lines],
            aggregates=[self._aggregate_to_model(entry) for entry in row.aggregates],
            issued_on=row.issued_on,
            valid_until=row.valid_until,
            authored_by=row.authored_by,
            submitted_at=self.timestamps.to_utc(row.submitted_at),
            validated_by=row.validated_by,
            validated_at=self.timestamps.to_utc(row.validated_at),
            planning_feedback=(
                UnplacedQuote.model_validate(row.planning_feedback)
                if row.planning_feedback
                else None
            ),
            interrupted_on=row.interrupted_on,
            auto_renew=row.auto_renew,
            renewed_from_id=row.renewed_from_id,
        )

    def _apply_fields(self, row: QuoteRow, model: Quote) -> None:
        """Write a quote's fields and children onto a row.

        Args:
            row (QuoteRow): The row to write to, carrying its identifier.
            model (Quote): The model carrying the values.

        Notes:
            Lines and aggregates are replaced wholesale rather than diffed.
            Both relationships are ``delete-orphan``, so assigning a new list
            removes what dropped out — which is what re-pricing a quote means,
            and far simpler to reason about than a merge.
        """
        self.logger.debug(
            "Applying a quote onto row %s (status %s).",
            row.id,
            model.status.value,
        )
        row.company_id = model.company_id
        row.reference = model.reference
        row.customer_id = model.customer_id
        row.status = model.status.value
        row.issued_on = model.issued_on
        row.valid_until = model.valid_until
        row.authored_by = model.authored_by
        row.submitted_at = model.submitted_at
        row.validated_by = model.validated_by
        row.validated_at = model.validated_at
        row.planning_feedback = (
            model.planning_feedback.model_dump(mode="json")
            if model.planning_feedback is not None
            else None
        )
        row.interrupted_on = model.interrupted_on
        row.auto_renew = model.auto_renew
        row.renewed_from_id = model.renewed_from_id
        row.lines = self._line_rows(row.id, model.lines)
        row.aggregates = self._aggregate_rows(row.id, model.aggregates)
        self.logger.info(
            "Stored quote row %s with %d line(s) and %d aggregate(s).",
            row.id,
            len(row.lines),
            len(row.aggregates),
        )
        if not model.lines:
            self.logger.warning(
                "Quote row %s is stored with no line: it prints as blank.",
                row.id,
            )
