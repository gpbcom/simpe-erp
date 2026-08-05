"""Planning runs and the interventions they produce.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-05

Notes:
    An intervention's address is **copied** onto the row rather than joined
    from the customer. A visit is a historical fact: if the customer moves next
    year, last month's planning must still say where the assistant actually
    went.

    ``interventions.planning_run_id`` cascades on delete because a run's
    visits have no meaning without the run that produced them, whereas
    ``hca_id`` cascading reflects that a deleted assistant's future visits must
    go with them — the plan has to be recomputed either way.
"""

from __future__ import annotations

# Standard library imports
from typing import Sequence, Union

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the planning tables."""
    op.create_table(
        "planning_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_travel_minutes", sa.Integer(), nullable=True),
        sa.Column("scheduled_count", sa.Integer(), nullable=True),
        sa.Column("unassigned_requirement_ids", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_planning_runs_status", "planning_runs", ["status"])
    op.create_index(
        "ix_planning_runs_period", "planning_runs", ["period_start", "period_end"]
    )

    op.create_table(
        "interventions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "planning_run_id",
            sa.String(36),
            sa.ForeignKey("planning_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("intervention_type_id", sa.String(36), nullable=False),
        sa.Column("quote_line_id", sa.String(36), nullable=False),
        sa.Column(
            "hca_id",
            sa.String(36),
            sa.ForeignKey("hcas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hca_full_name", sa.String(255), nullable=False),
        sa.Column("customer_id", sa.String(36), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("street", sa.String(255), nullable=False),
        sa.Column("postal_code", sa.String(16), nullable=False),
        sa.Column("city", sa.String(128), nullable=False),
        sa.Column("country", sa.String(128), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("geocoding_error", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
    )
    op.create_index("ix_interventions_hca_day", "interventions", ["hca_id", "day"])
    op.create_index("ix_interventions_run", "interventions", ["planning_run_id"])
    op.create_index("ix_interventions_day", "interventions", ["day"])
    op.create_index("ix_interventions_customer", "interventions", ["customer_id"])


def downgrade() -> None:
    """Drop the planning tables, children first."""
    op.drop_table("interventions")
    op.drop_table("planning_runs")
