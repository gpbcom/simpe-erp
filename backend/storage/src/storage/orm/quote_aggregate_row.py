from __future__ import annotations

# Standard library imports
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

# Third-party imports
from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

# First-party imports
from storage.orm.base import Base

if TYPE_CHECKING:
    # First-party imports
    from storage.orm.quote_row import QuoteRow


class QuoteAggregateRow(Base):
    """The ``quote_type_week_aggregates`` table.

    Attributes:
        id (str): UUID primary key.
        quote_id (str): The quote these totals belong to.
        intervention_type_id (str): The type the totals cover.
        intervention_type_name (str): Its name, copied at the time of pricing.
        iso_year (int): ISO year of the week.
        iso_week (int): ISO week number.
        week_start_date (date): The Monday of that ISO week.
        line_count (int): How many lines were summed.
        total_minutes (int): Total service time in the week.
        total_ht (Decimal): Total excluding tax.
        vat_amount (Decimal): Total tax.
        total_ttc (Decimal): Total including tax.
        quote (QuoteRow): The owning quote.

    Notes:
        Derived from the lines, but persisted. A reprinted quote must show what
        it showed when issued, and recomputing would pick up a type that has
        since been renamed or repriced.

        The type's name is a **copy**, and there is deliberately no foreign key
        on ``intervention_type_id`` here: the aggregate is a printed figure,
        not a live reference, and the line table already holds the constraint.

        ``(quote_id, intervention_type_id, iso_year, iso_week)`` is unique —
        one row per type per week is the whole point, and a duplicate would
        double a subtotal on the printed quote.
    """

    __tablename__ = "quote_type_week_aggregates"
    __table_args__ = (
        Index("ix_quote_aggregates_quote_id", "quote_id"),
        Index(
            "ix_quote_aggregates_unique",
            "quote_id",
            "intervention_type_id",
            "iso_year",
            "iso_week",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    quote_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
    )
    intervention_type_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH), nullable=False
    )
    intervention_type_name: Mapped[str] = mapped_column(String(255), nullable=False)
    iso_year: Mapped[int] = mapped_column(Integer, nullable=False)
    iso_week: Mapped[int] = mapped_column(Integer, nullable=False)
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_ht: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_ttc: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    quote: Mapped[QuoteRow] = relationship(back_populates="aggregates")
