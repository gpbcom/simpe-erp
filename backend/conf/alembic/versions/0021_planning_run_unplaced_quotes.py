"""Record which quotes a run could not fit, and why.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-10

Notes:
    A planning run used to fail outright the moment one visit could not be
    placed. The whole week was withheld and the operator got a single long
    sentence quoting a solver status and a configuration key — accurate,
    unreadable, and impossible to act on without knowing what a deterministic
    budget is.

    The run now stores the plan it managed and finishes ``partial``. This
    column is what makes that safe: it holds one entry per quote whose work
    could not all be fitted, each naming the customer, the visits and the
    reason for each. Without it the screen would have to re-run the diagnosis
    to say anything, and a plan with a silent gap in it is exactly the
    outcome the old all-or-nothing rule existed to prevent.

    JSON rather than columns or a joined string, because the shape is nested —
    a quote holds visits, and each visit holds its own reason and detail.
    Flattening that into text would mean inventing a format and parsing it
    back.

    Nullable, and read as an empty list. Every run that predates this
    revision either succeeded, in which case there is nothing to report, or
    failed with its explanation already in ``error_message``.
"""

from __future__ import annotations

# Third-party imports
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the unplaced-quote report to the planning runs table."""
    op.add_column(
        "planning_runs",
        sa.Column(
            "unplaced_quotes",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove the unplaced-quote report."""
    op.drop_column("planning_runs", "unplaced_quotes")
