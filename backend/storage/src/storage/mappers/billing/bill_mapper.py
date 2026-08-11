from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from logging import Logger
from typing import List, Optional
from uuid import uuid4

# First-party imports
from models.billing.bill import Bill
from models.billing.bill_line import BillLine
from models.geo.postal_address import PostalAddress
from storage.mappers.base_mapper import BaseMapper
from storage.orm.billing.bill_line_row import BillLineRow
from storage.orm.billing.bill_row import BillRow


class BillMapper(BaseMapper[Bill, BillRow]):
    """Converts an invoice and its charges to and from their rows.

    Notes:
        - The charges are replaced wholesale rather than diffed, as a quote's
          lines are. The relationship is ``delete-orphan``, so assigning a new
          list removes what dropped out.
        - In practice an issued invoice's charges never change: it is a legal
          document, and a correction is a credit note. The wholesale write is
          what makes the *generation* path simple, not an invitation to edit.
        - The customer's address is flattened onto columns and rebuilt on the
          way back, exactly as a visit's is. Rebuilding it issues no geocoding
          request — the stored coordinates come back as they were written, which
          :class:`~models.geo.postal_address.PostalAddress` treats as nothing to
          look up. That matters on a bill list, which loads dozens at once.
        - A charge keeps its own identifier when it has one, so re-reading an
          invoice never renumbers rows a customer has already seen.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(model_class=Bill, row_class=BillRow, logger=logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _line_to_model(self, row: BillLineRow) -> BillLine:
        """Build one charge from a row's columns.

        Args:
            row (BillLineRow): The row to read.

        Returns:
            BillLine: The domain model.
        """
        return BillLine(
            id=row.id,
            quote_line_id=row.quote_line_id,
            intervention_id=row.intervention_id,
            name=row.name,
            service_category=row.service_category,
            service_date=row.service_date,
            day=row.day,
            start_time=row.start_time,
            end_time=row.end_time,
            hca_full_name=row.hca_full_name,
            duration_minutes=row.duration_minutes,
            hourly_rate_ht=row.hourly_rate_ht,
            total_ht=row.total_ht,
            vat_rate=row.vat_rate,
            vat_amount=row.vat_amount,
            total_ttc=row.total_ttc,
        )

    def _line_rows(self, bill_id: str, lines: List[BillLine]) -> List[BillLineRow]:  # noqa: E501
        """Build the charge rows for an invoice.

        Args:
            bill_id (str): The owning invoice's identifier.
            lines (List[BillLine]): The charges to store.

        Returns:
            List[BillLineRow]: Rows carrying their printed position.

        Notes:
            The position is the index rather than anything derived from the
            dates, so the order the document was rendered in is the order it
            comes back in. An invoice reprinted in a different order from the
            one the customer holds is a support call nobody can settle.
        """
        stamped = datetime.now(UTC)
        return [
            BillLineRow(
                id=line.id if line.id else str(uuid4()),
                bill_id=bill_id,
                position=position,
                quote_line_id=line.quote_line_id,
                intervention_id=line.intervention_id,
                name=line.name,
                service_category=line.service_category.value,
                service_date=line.service_date,
                day=line.day,
                start_time=line.start_time,
                end_time=line.end_time,
                hca_full_name=line.hca_full_name,
                duration_minutes=line.duration_minutes,
                hourly_rate_ht=line.hourly_rate_ht,
                total_ht=line.total_ht,
                vat_rate=line.vat_rate,
                vat_amount=line.vat_amount,
                total_ttc=line.total_ttc,
                created_at=stamped,
                updated_at=stamped,
            )
            for position, line in enumerate(lines)
        ]

    def _build_model(self, row: BillRow) -> Bill:
        """Build an invoice from a row's columns and its charges.

        Args:
            row (BillRow): The row to read.

        Returns:
            Bill: The domain model.
        """
        self.logger.debug(
            "Building a bill from row %s (number %s, status %s).",
            row.id,
            row.number,
            row.status,
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
        return Bill(
            id=row.id,
            company_id=row.company_id,
            customer_id=row.customer_id,
            billing_run_id=row.billing_run_id,
            number=row.number,
            sequence=row.sequence,
            sequence_year=row.sequence_year,
            periodicity=row.periodicity,
            period_start=row.period_start,
            period_end=row.period_end,
            issued_on=row.issued_on,
            due_on=row.due_on,
            status=row.status,
            customer_full_name=row.customer_full_name,
            customer_address=address,
            lines=[self._line_to_model(line) for line in row.lines],
            total_ht=row.total_ht,
            total_vat=row.total_vat,
            total_ttc=row.total_ttc,
            document_key=row.document_key,
            generated_by=row.generated_by,
            validated_by=row.validated_by,
            validated_at=self.timestamps.to_utc(row.validated_at),
            sent_at=self.timestamps.to_utc(row.sent_at),
            paid_on=row.paid_on,
            created_at=self.timestamps.to_utc(row.created_at),
            updated_at=self.timestamps.to_utc(row.updated_at),
        )

    def _apply_fields(self, row: BillRow, model: Bill) -> None:
        """Write an invoice's fields and charges onto a row.

        Args:
            row (BillRow): The row to write to, carrying its identifier.
            model (Bill): The model carrying the values.

        Notes:
            The number and the series position are written like any other
            column, but they are the one part a caller must not invent: they
            come from
            :meth:`~storage.repositories.billing.bill.BillRepository.next_number`,
            which allocates them under a lock. Writing them here without having
            gone through it is what leaves a gap in the legal series.
        """
        self.logger.debug(
            "Applying a bill onto row %s (number %s, status %s).",
            row.id,
            model.number,
            model.status.value,
        )
        row.company_id = model.company_id
        row.customer_id = model.customer_id
        row.billing_run_id = model.billing_run_id
        row.number = model.number
        row.sequence = model.sequence
        row.sequence_year = model.sequence_year
        row.periodicity = model.periodicity.value
        row.period_start = model.period_start
        row.period_end = model.period_end
        row.issued_on = model.issued_on
        row.due_on = model.due_on
        row.status = model.status.value
        row.customer_full_name = model.customer_full_name
        row.street = model.customer_address.street
        row.postal_code = model.customer_address.postal_code
        row.city = model.customer_address.city
        row.country = model.customer_address.country
        row.latitude = model.customer_address.latitude
        row.longitude = model.customer_address.longitude
        row.geocoding_error = model.customer_address.geocoding_error
        row.total_ht = model.total_ht
        row.total_vat = model.total_vat
        row.total_ttc = model.total_ttc
        row.document_key = model.document_key
        row.generated_by = model.generated_by
        row.validated_by = model.validated_by
        row.validated_at = model.validated_at
        row.sent_at = model.sent_at
        row.paid_on = model.paid_on
        row.lines = self._line_rows(row.id, model.lines)
        if not model.document_key:
            self.logger.warning(
                "Storing bill row %s with no document: it cannot be validated "
                "or downloaded until one is attached.",
                row.id,
            )
