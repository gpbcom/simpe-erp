"""Intervention-type catalog.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-05

Notes:
    The rate is ``Numeric(12, 3)`` rather than the two decimals an amount uses:
    the contractual base rate is ``31.905`` €/h, and rounding the column to
    cents would silently change the price of every hour billed.
"""

from __future__ import annotations

# Standard library imports
from typing import Optional, Sequence, Union

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Optional[str] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the intervention-type catalog."""
    op.create_table(
        "intervention_types",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("service_category", sa.String(16), nullable=False),
        sa.Column("base_hourly_rate_ht", sa.Numeric(12, 3), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_intervention_types_name_unique", "intervention_types", ["name"], unique=True
    )
    op.create_index(
        "ix_intervention_types_code_unique", "intervention_types", ["code"], unique=True
    )
    op.create_index(
        "ix_intervention_types_is_active", "intervention_types", ["is_active"]
    )


def downgrade() -> None:
    """Drop the intervention-type catalog."""
    op.drop_table("intervention_types")
