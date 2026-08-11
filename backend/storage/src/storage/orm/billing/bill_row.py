from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

# Third-party imports
from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# First-party imports
from storage.orm.base import Base

if TYPE_CHECKING:
    # First-party imports
    from storage.orm.billing.bill_line_row import BillLineRow


class BillRow(Base):
    """The ``bills`` table.

    Attributes:
        id (str): UUID primary key.
        company_id (str): The agency that issued it.
        customer_id (str): The customer it is addressed to.
        billing_run_id (Optional[str]): The run that produced it.
        number (str): Human-facing invoice number; unique.
        sequence (int): Position in the agency's yearly series.
        sequence_year (int): The year the series belongs to.
        periodicity (str): The rule the billed window came from.
        period_start (date): First day billed.
        period_end (date): Last day billed.
        issued_on (date): The invoice date.
        due_on (date): The day payment falls due.
        status (str): Where the invoice has reached commercially.
        customer_full_name (str): The customer's name, as addressed.
        street (str): Street line of where the invoice was addressed.
        postal_code (str): Postal code of where it was addressed.
        city (str): City of where it was addressed.
        country (str): Country of where it was addressed.
        latitude (Optional[float]): Resolved latitude, when geocoded.
        longitude (Optional[float]): Resolved longitude, when geocoded.
        geocoding_error (Optional[str]): Stable geocoding failure code.
        total_ht (Decimal): Invoice total excluding tax.
        total_vat (Decimal): Total tax.
        total_ttc (Decimal): Invoice total including tax.
        document_key (Optional[str]): Where the rendered document is stored.
        generated_by (Optional[str]): The account that ran the generation.
        validated_by (Optional[str]): The account that approved it.
        validated_at (Optional[datetime]): When it was approved.
        sent_at (Optional[datetime]): When it was emailed to the customer.
        paid_on (Optional[date]): The day it was settled.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.
        lines (List[BillLineRow]): The visits charged.

    Notes:
        - **Three unique indexes, and each prevents a different accident.**
          ``(customer_id, period_start, period_end)`` is what actually stops a
          customer being billed twice for one period when two runs race past the
          service's own check. ``number`` and
          ``(company_id, sequence_year, sequence)`` guard the legal series,
          which French invoicing requires to be unbroken and chronological —
          two runs allocating the same position must fail loudly rather than
          leave a gap nobody can explain.
        - The customer foreign key **restricts** rather than cascading, as the
          quote's does. Deleting a billed customer would erase accounting
          history, and that is an operator's decision to take deliberately, not
          a side effect of tidying a list.
        - ``billing_run_id``, ``generated_by`` and ``validated_by`` are **not**
          foreign keys. Purging old runs must never take an invoice with it, and
          "who approved this?" is an audit trail that has to outlive the account
          of whoever left the agency.
        - The customer's address is **flattened and copied**, exactly as an
          intervention copies the one it is delivered at. A customer who moves
          must not retroactively change where last quarter's invoice was sent.
        - There is no cancelled state and no delete path in ordinary use. A
          mistaken invoice is corrected by a credit note, because a number
          withdrawn from the series is the gap the series forbids.
    """

    __tablename__ = "bills"
    __table_args__ = (
        Index("ix_bills_number_unique", "number", unique=True),
        Index(
            "ix_bills_sequence_unique",
            "company_id",
            "sequence_year",
            "sequence",
            unique=True,
        ),
        Index(
            "ix_bills_customer_period_unique",
            "customer_id",
            "period_start",
            "period_end",
            unique=True,
        ),
        Index("ix_bills_company_status", "company_id", "status"),
        Index("ix_bills_period", "period_start", "period_end"),
        Index("ix_bills_run", "billing_run_id"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)
    customer_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    billing_run_id: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence_year: Mapped[int] = mapped_column(Integer, nullable=False)
    periodicity: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    issued_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    customer_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    street: Mapped[str] = mapped_column(String(255), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(16), nullable=False)
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(128), nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    geocoding_error: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    total_ht: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_ttc: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    document_key: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    generated_by: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
    validated_by: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
    validated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    lines: Mapped[List[BillLineRow]] = relationship(
        back_populates="bill",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="BillLineRow.position",
    )
