from __future__ import annotations

# Standard library imports
from datetime import date, time
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

# Third-party imports
from sqlalchemy import (
    JSON,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Time,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

# First-party imports
from storage.orm.base import Base

if TYPE_CHECKING:
    # First-party imports
    from storage.orm.quoting.quote_row import QuoteRow


class QuoteLineRow(Base):
    """The ``quote_lines`` table.

    Attributes:
        id (str): UUID primary key.
        quote_id (str): The quote this line belongs to.
        position (int): Order on the printed quote.
        name (str): What the service is.
        intervention_type_id (str): The catalog entry it sells.
        service_category (str): What kind of care it is, deciding its VAT rate.
        service_date (date): The day the service is delivered.
        earliest_start (time): Earliest the service may begin.
        latest_end (time): Latest the service may finish.
        duration_minutes (int): How long the service takes.
        hourly_rate_ht (Optional[Decimal]): Rate billed, surcharge included.
        total_ht (Optional[Decimal]): Line total excluding tax.
        vat_amount (Optional[Decimal]): Tax on the line.
        total_ttc (Optional[Decimal]): Line total including tax.
        required_skill_codes (Optional[List[str]]): Skills this line requires,
            or ``NULL`` to inherit the catalog entry's.
        required_certification_codes (Optional[List[str]]): Codes this line
            requires, or ``NULL`` to inherit the catalog entry's.
        quote (QuoteRow): The owning quote.

    Notes:
        - The amounts are **stored**, not recomputed on read. An issued quote
          must reprint identically after its intervention type is repriced, so
          the figures are frozen at the moment the quote was priced.
        - The intervention-type foreign key restricts. A type is retired with a
          flag rather than deleted precisely so this reference stays valid. The
          constraint is what makes that a rule rather than a convention.
        - ``position`` exists because a quote is a document. The order the
          operator entered the services in is what the customer reads, and a
          natural key ordering would silently reshuffle it.
    """

    __tablename__ = "quote_lines"
    __table_args__ = (
        Index("ix_quote_lines_quote_id", "quote_id"),
        Index("ix_quote_lines_service_date", "service_date"),
        Index("ix_quote_lines_intervention_type", "intervention_type_id"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    quote_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    intervention_type_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("intervention_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    service_category: Mapped[str] = mapped_column(String(16), nullable=False)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    earliest_start: Mapped[time] = mapped_column(Time, nullable=False)
    latest_end: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    hourly_rate_ht: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    total_ht: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    vat_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    total_ttc: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    required_certification_codes: Mapped[Optional[List[str]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    required_skill_codes: Mapped[Optional[List[str]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )

    quote: Mapped[QuoteRow] = relationship(back_populates="lines")
