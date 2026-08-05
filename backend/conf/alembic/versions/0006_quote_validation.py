"""Quote authorship and the manager validation step.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-05

Notes:
    An assistant can now write a quote, which a manager then validates. That
    needs four columns — who wrote it, when they submitted it, who approved it
    and when — and a wider ``status`` column to hold the new
    ``pending-validation`` value.

    **The widening is the load-bearing part of this revision.** ``status`` was
    ``String(16)``, sized when the longest value was ``accepted``.
    ``pending-validation`` is eighteen characters: PostgreSQL refuses the write
    outright, while SQLite silently truncates it. Without this migration the
    feature would pass its tests on the in-memory SQLite the suite uses and fail
    the moment it met the real database.

    ``authored_by`` and ``validated_by`` carry no foreign key, matching
    ``planning_runs.requested_by``. They are an audit trail: an administrator
    leaving the agency must not take with them the record of which quotes they
    approved, nor have their account become undeletable because of it.
"""

from __future__ import annotations

# Standard library imports
from typing import Sequence, Union

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Widen the status column and add the four workflow columns."""
    with op.batch_alter_table("quotes") as batch:
        batch.alter_column(
            "status",
            existing_type=sa.String(16),
            type_=sa.String(32),
            existing_nullable=False,
        )
    op.add_column("quotes", sa.Column("authored_by", sa.String(36), nullable=True))
    op.add_column(
        "quotes",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("quotes", sa.Column("validated_by", sa.String(36), nullable=True))
    op.add_column(
        "quotes",
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_quotes_authored_by", "quotes", ["authored_by"])


def downgrade() -> None:
    """Drop the workflow columns and narrow the status column again.

    Notes:
        Any quote sitting in ``pending-validation`` is moved back to ``draft``
        first. Narrowing the column under it would truncate the value into
        something no enum recognises, which reads back as a quote in no state
        at all — worse than losing the fact that it had been submitted.
    """
    op.execute(
        "UPDATE quotes SET status = 'draft' WHERE status = 'pending-validation'"
    )
    op.drop_index("ix_quotes_authored_by", table_name="quotes")
    op.drop_column("quotes", "validated_at")
    op.drop_column("quotes", "validated_by")
    op.drop_column("quotes", "submitted_at")
    op.drop_column("quotes", "authored_by")
    with op.batch_alter_table("quotes") as batch:
        batch.alter_column(
            "status",
            existing_type=sa.String(32),
            type_=sa.String(16),
            existing_nullable=False,
        )
