"""Let one customer be invoiced on a different granularity from the rest.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-11

Notes:
    The invoicing periodicity arrived in 0023 as an agency-wide rule, which is
    the right default and the wrong ceiling: a household paying week by week and
    an institution wanting one document a year are both ordinary, and neither
    can be served by a single setting.

    **The column is nullable, and null is the ordinary case.** It is an
    override, so backfilling it with the agency's current periodicity would be
    wrong in a way nothing would report — every existing customer would carry a
    frozen copy of today's setting, and none of them would follow it when a
    manager changed it. Null means "whatever the agency bills on", which is what
    every row means today and what almost every row will go on meaning.

    Nothing is re-issued. An invoice already written keeps the period it was
    written for; changing a customer's granularity decides what the *next* run
    bills them over, which is why this migration touches no existing invoice.
"""

from __future__ import annotations

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the per-customer billing periodicity."""
    op.add_column(
        "customers",
        sa.Column("billing_periodicity", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    """Drop the per-customer billing periodicity.

    Notes:
        Every customer goes back to the agency's own rule. That loses which of
        them had been put on a different one — a decision somebody took, not a
        derived value — so the undo is safe for the invoices already issued and
        lossy for the arrangement behind them.
    """
    op.drop_column("customers", "billing_periodicity")
