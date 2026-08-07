"""Quotes, their lines and their per-type weekly totals.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-05

Notes:
    Line amounts are ``Numeric(12, 2)`` — they are money. The intervention
    type's *rate* is three decimals (see 0002), because the contractual base
    rate is 31.905 €/h; a line total is a rounded amount and two decimals is
    correct for it.
"""

from __future__ import annotations

# Standard library imports
from typing import Optional, Sequence, Union

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Optional[str] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the quote tables."""
    op.create_table(
        "quotes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("reference", sa.String(64), nullable=False),
        sa.Column(
            "customer_id",
            sa.String(36),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_quotes_reference_unique", "quotes", ["reference"], unique=True)
    op.create_index("ix_quotes_customer_status", "quotes", ["customer_id", "status"])
    op.create_index("ix_quotes_status", "quotes", ["status"])

    op.create_table(
        "quote_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "quote_id",
            sa.String(36),
            sa.ForeignKey("quotes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "intervention_type_id",
            sa.String(36),
            sa.ForeignKey("intervention_types.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("earliest_start", sa.Time(), nullable=False),
        sa.Column("latest_end", sa.Time(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("hourly_rate_ht", sa.Numeric(12, 2), nullable=True),
        sa.Column("total_ht", sa.Numeric(12, 2), nullable=True),
        sa.Column("vat_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("total_ttc", sa.Numeric(12, 2), nullable=True),
    )
    op.create_index("ix_quote_lines_quote_id", "quote_lines", ["quote_id"])
    op.create_index("ix_quote_lines_service_date", "quote_lines", ["service_date"])
    op.create_index(
        "ix_quote_lines_intervention_type", "quote_lines", ["intervention_type_id"]
    )

    op.create_table(
        "quote_type_week_aggregates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "quote_id",
            sa.String(36),
            sa.ForeignKey("quotes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("intervention_type_id", sa.String(36), nullable=False),
        sa.Column("intervention_type_name", sa.String(255), nullable=False),
        sa.Column("iso_year", sa.Integer(), nullable=False),
        sa.Column("iso_week", sa.Integer(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("total_minutes", sa.Integer(), nullable=False),
        sa.Column("total_ht", sa.Numeric(12, 2), nullable=False),
        sa.Column("vat_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_ttc", sa.Numeric(12, 2), nullable=False),
    )
    op.create_index(
        "ix_quote_aggregates_quote_id", "quote_type_week_aggregates", ["quote_id"]
    )
    op.create_index(
        "ix_quote_aggregates_unique",
        "quote_type_week_aggregates",
        ["quote_id", "intervention_type_id", "iso_year", "iso_week"],
        unique=True,
    )


def downgrade() -> None:
    """Drop the quote tables, children first."""
    op.drop_table("quote_type_week_aggregates")
    op.drop_table("quote_lines")
    op.drop_table("quotes")
