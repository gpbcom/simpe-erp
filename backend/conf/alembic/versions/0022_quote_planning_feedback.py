"""Tell a quote why its work would not fit, and when it could.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-10

Notes:
    An accepted quote whose work the planner cannot place is not a settled
    commitment: the agency has agreed to something it cannot currently do.
    Such a quote now goes back to ``pending-validation``, into the queue a
    manager already works through.

    This column is what makes that intelligible. A quote reappearing in the
    validation queue a week after it was validated, with no explanation, reads
    as the system having lost it. Stored here instead are the visits that
    could not be placed, the reason for each, and up to three times a
    qualified assistant is free — so the person picking it up can telephone
    the customer with something to propose rather than only a problem to
    report.

    JSON, because the shape is nested and read whole: a quote holds visits,
    each visit holds a reason, and beside them is a list of offered slots.
    None of it is queried on its own.

    **``jsonb`` rather than ``json``, and the difference is load-bearing.**
    The schedulable-quote query selects DISTINCT over whole rows, and
    PostgreSQL has no equality operator for ``json`` — so a plain JSON column
    here stopped every planning run from loading any work at all, with the
    only symptom a run that reported nothing to schedule. ``jsonb`` compares.

    Nullable, and cleared when the work fits again. A quote with no note is
    the ordinary case, and the absence of a note is the absence of a problem.

    **The slots are offers, not bookings.** Nothing is reserved by writing
    them: two operators acting on the same suggestion are both told it fits,
    and the next planning run settles it. Reserving would need an expiry, a
    release path and a screen showing what is held — a reservation system, to
    answer something a telephone call resolves.
"""

from __future__ import annotations

# Third-party imports
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the planning feedback column to the quotes table."""
    op.add_column(
        "quotes",
        sa.Column(
            "planning_feedback",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove the planning feedback column."""
    op.drop_column("quotes", "planning_feedback")
