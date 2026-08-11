from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from typing import Optional

# Third-party imports
from sqlalchemy import JSON, Date, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class BillingRunRow(Base):
    """The ``billing_runs`` table.

    Attributes:
        id (str): UUID primary key.
        company_id (str): The agency whose customers are being billed.
        requested_by (Optional[str]): The account that asked for the run.
        status (str): Where the run has got to.
        reference_date (date): The day the window was resolved from.
        periodicity (str): The rule the window came from.
        period_start (date): First day billed.
        period_end (date): Last day billed.
        bill_ids (Optional[list]): The invoices the run wrote.
        failed_customer_ids (Optional[list]): The customers it could not bill.
        error_message (Optional[str]): Why the run failed, when it did.
        requested_at (datetime): When it was asked for.
        started_at (Optional[datetime]): When a worker picked it up.
        finished_at (Optional[datetime]): When it reached a terminal status.

    Notes:
        - ``company_id`` is stored rather than reached through ``requested_by``,
          and neither is a foreign key. A manager leaving the agency must not
          take the record of which months they billed with them, nor block their
          own account being deleted — the same reasoning the planning run makes.
        - **Both outcome lists are kept, and as JSON rather than as tables.**
          They are only ever read back whole, alongside the run, and a partial
          month is only actionable if something says *which* customers went
          unbilled. A count would leave somebody comparing two lists by hand.
        - The window is stored rather than recomputed from ``reference_date``
          and ``periodicity``. An agency that changes its periodicity afterwards
          would otherwise see a run claiming to have billed a period it never
          touched.
    """

    __tablename__ = "billing_runs"
    __table_args__ = (
        Index("ix_billing_runs_status", "status"),
        Index("ix_billing_runs_company", "company_id", "status"),
        Index("ix_billing_runs_period", "period_start", "period_end"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)
    requested_by: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reference_date: Mapped[date] = mapped_column(Date, nullable=False)
    periodicity: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    bill_ids: Mapped[Optional[list]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    failed_customer_ids: Mapped[Optional[list]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
