"""Record whether a stored plan's travel was ever proved minimal.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-10

Notes:
    A planning run is now solved in two passes: the first places every visit,
    the second shortens the driving. The second may run out of budget, in
    which case the first pass's plan is stored unchanged — every visit
    scheduled, the travel simply never proved minimal.

    That outcome needs recording, because it is invisible from the plan
    itself. A week with slightly longer rounds looks exactly like a week whose
    rounds are as short as they can be, and the difference only shows up as a
    slow creep in the travel figure that nobody can attribute. The column is
    what lets the screen say "not optimised" rather than leaving an operator
    to wonder.

    **Nullable, and null is not false.** Every run that predates this
    revision was solved by a single pass that never asked the question, so
    there is no honest value to backfill. False would assert that those plans
    were found wanting, which nothing established. The screen renders null the
    way it always did.
"""

from __future__ import annotations

# Third-party imports
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the optimality column to the planning runs table."""
    op.add_column(
        "planning_runs",
        sa.Column("is_optimised", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    """Remove the optimality column."""
    op.drop_column("planning_runs", "is_optimised")
