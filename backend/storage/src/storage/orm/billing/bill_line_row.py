from __future__ import annotations

# Standard library imports
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

# Third-party imports
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# First-party imports
from storage.orm.base import Base

if TYPE_CHECKING:
    # First-party imports
    from storage.orm.billing.bill_row import BillRow


class BillLineRow(Base):
    """The ``bill_lines`` table.

    Attributes:
        id (str): UUID primary key.
        bill_id (str): The invoice this charge belongs to.
        position (int): Order on the printed invoice.
        quote_line_id (str): The quote line the charge came from.
        intervention_id (Optional[str]): The visit that delivered it.
        name (str): What the service is.
        service_category (str): What kind of care it is.
        service_date (date): The day the service was sold for.
        day (Optional[date]): The day it was actually delivered.
        start_time (Optional[time]): When the delivered visit began.
        end_time (Optional[time]): When the delivered visit ended.
        hca_full_name (Optional[str]): Who delivered it.
        duration_minutes (int): How long the service takes.
        hourly_rate_ht (Decimal): Rate billed, surcharge included.
        total_ht (Decimal): Line total excluding tax.
        vat_rate (Decimal): The rate the tax was charged at.
        vat_amount (Decimal): Tax on the line.
        total_ttc (Decimal): Line total including tax.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.
        bill (BillRow): The owning invoice.

    Notes:
        - **``quote_line_id`` and ``intervention_id`` are plain columns, not
          foreign keys.** A quote line may be edited or removed after the
          invoice was issued, and an intervention *will* be — re-planning a
          period deletes and rewrites every visit in it, so a real key would
          either cascade the invoice line away or block the replan. Both are
          provenance, and an invoice is a record of what was charged rather
          than a live join.
        - The amounts are **not nullable**, unlike a quote line's. An invoice
          with a blank amount column is a legal defect, so the shape of the
          table says so.
        - ``vat_rate`` carries four decimals where the money carries two:
          5.5% is stored as ``0.0550``, and rounding it to the cent would make
          every reduced-rate line look tax-free.
        - ``position`` exists because an invoice is a document. The order the
          charges are printed in is what the customer reads, and a natural key
          ordering would reshuffle it between reprints.
    """

    __tablename__ = "bill_lines"
    __table_args__ = (
        Index("ix_bill_lines_bill_id", "bill_id"),
        Index("ix_bill_lines_service_date", "service_date"),
        Index("ix_bill_lines_quote_line", "quote_line_id"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    bill_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("bills.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quote_line_id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)
    intervention_id: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    service_category: Mapped[str] = mapped_column(String(16), nullable=False)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    end_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    hca_full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    hourly_rate_ht: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_ht: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_ttc: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    bill: Mapped[BillRow] = relationship(back_populates="lines")
