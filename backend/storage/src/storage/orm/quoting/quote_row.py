from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

# Third-party imports
from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

# First-party imports
from storage.orm.base import Base

if TYPE_CHECKING:
    # First-party imports
    from storage.orm.quoting.quote_aggregate_row import QuoteAggregateRow
    from storage.orm.quoting.quote_line_row import QuoteLineRow


class QuoteRow(Base):
    """The ``quotes`` table.

    Attributes:
        id (str): UUID primary key.
        company_id (str): The agency that offers the work.
        team_id (str): The team that will deliver it.
        reference (str): Human-facing quote number; unique.
        customer_id (str): The customer the offer is addressed to.
        status (str): Where the quote is in its lifecycle.
        issued_on (Optional[date]): The day the quote was sent.
        valid_until (Optional[date]): The day the offer lapses.
        authored_by (Optional[str]): The account that wrote the quote.
        submitted_at (Optional[datetime]): When it went for validation.
        validated_by (Optional[str]): The account that validated it.
        validated_at (Optional[datetime]): When it was validated.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.
        lines (List[QuoteLineRow]): The services offered.
        aggregates (List[QuoteAggregateRow]): The per-type, per-week totals.

    Notes:
        - The customer foreign key restricts rather than cascades. Deleting a
          customer who has been quoted would erase the commercial history, and
          that is an operator decision to make deliberately, not a side effect.
        - Both children cascade: a line or an aggregate has no meaning without
          the quote it belongs to.
        - ``(customer_id, status)`` is indexed because the planner asks for every
          accepted quote, and a customer screen asks for one customer's quotes.
        - ``company_id`` is denormalised rather than reached through
          ``authored_by``. That column is deliberately nullable — an author who
          leaves must not take their quotes with them — so it cannot be the path
          by which the planner decides whose work a quote is. ``(company_id,
          status)`` is what the planner's own query filters on.
        - ``team_id`` is denormalised for exactly the same reason, one level
          down: a run schedules one team's accepted work, and reaching the team
          through the customer's nearest site would recompute an attribution
          decision that was taken once, at creation, and may since have been
          changed deliberately. It carries **no foreign key**, matching
          ``company_id`` beside it — the team is refused deletion while it still
          holds quotes, which is a service's refusal rather than a cascade
          nobody confirmed.
    """

    __tablename__ = "quotes"
    __table_args__ = (
        Index("ix_quotes_reference_unique", "reference", unique=True),
        Index("ix_quotes_customer_status", "customer_id", "status"),
        Index("ix_quotes_company_status", "company_id", "status"),
        Index("ix_quotes_status", "status"),
        Index("ix_quotes_authored_by", "authored_by"),
        Index("ix_quotes_auto_renew", "auto_renew", "valid_until"),
        Index("ix_quotes_team_status", "team_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)
    team_id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)
    reference: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    issued_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    authored_by: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    validated_by: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
    planning_feedback: Mapped[Optional[dict]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    interrupted_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # noqa: E501
    renewed_from_id: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
    validated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    lines: Mapped[List[QuoteLineRow]] = relationship(
        back_populates="quote",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="QuoteLineRow.position",
    )
    aggregates: Mapped[List[QuoteAggregateRow]] = relationship(
        back_populates="quote",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
