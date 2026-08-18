"""Move the VAT category from the catalog entry onto the quote line.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-06

Notes:
    The same service is necessity care for one customer and comfort care for
    another — help with washing under a care plan is billed at the reduced
    rate, and the same hour arranged privately is not. So the rate cannot be a
    property of the service being sold. It is decided when the quote is
    written, by the person who knows which the customer is.

    **Added nullable, backfilled, then made NOT NULL.** Adding a non-nullable
    column outright fails on any table with rows in it, and this one holds
    every quote line the agency has ever written.

    The backfill reads each line's catalog entry, which is where the category
    lived until now. That reproduces exactly the VAT every existing quote was
    priced at, so no issued quote changes its total — a customer is never
    re-billed for work already quoted.
"""

from __future__ import annotations

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the column, backfill it from the catalog, then require it."""
    op.add_column(
        "quote_lines",
        sa.Column("service_category", sa.String(length=16), nullable=True),
    )
    op.execute(
        """
        UPDATE quote_lines
           SET service_category = (
               SELECT intervention_types.service_category
                 FROM intervention_types
                WHERE intervention_types.id = quote_lines.intervention_type_id
           )
         WHERE service_category IS NULL
        """
    )
    # A line whose catalog entry has since been deleted would still be null.
    # `RESTRICT` on the foreign key means that cannot happen today, but the
    # migration must not fail on a database where it somehow did — and
    # necessity is the safer default of the two: it under-charges VAT rather
    # than over-charging a family entitled to the reduced rate, and it is
    # visible on screen for somebody to correct.
    op.execute(
        "UPDATE quote_lines SET service_category = 'necessity' "
        "WHERE service_category IS NULL"
    )
    # Through `batch_alter_table`, as everywhere else here: SQLite has no
    # `ALTER COLUMN`, so Alembic rebuilds the table instead. The migration test
    # suite runs against SQLite, and PostgreSQL is what production runs — a
    # migration that only works on one of them is one nobody can test.
    with op.batch_alter_table("quote_lines") as batch:
        batch.alter_column(
            "service_category",
            existing_type=sa.String(length=16),
            nullable=False,
        )


def downgrade() -> None:
    """Drop the column, returning the category to the catalog entry alone."""
    with op.batch_alter_table("quote_lines") as batch:
        batch.drop_column("service_category")
