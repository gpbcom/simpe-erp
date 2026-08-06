"""Let a quote be ended early, and let one renew itself.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-06

Notes:
    Three columns on ``quotes``:

    - ``interrupted_on`` — the last day the arrangement is delivered. Services
      dated after it are neither planned nor billed. Nullable, because most
      quotes simply run to their end.
    - ``auto_renew`` — whether a successor is written when the quote expires.
      ``NOT NULL`` with a server-side default of false: renewal is something a
      customer opts into, and a null read as "maybe" would eventually be read
      as "yes" by somebody's ``if row.auto_renew`` on a database that predates
      the column.
    - ``renewed_from_id`` — the quote a successor was written from, so a chain
      of renewals can be walked back to the arrangement it started as.

    ``renewed_from_id`` carries **no foreign key**. It points at a quote that
    may be deleted years later, and a constraint would either block that
    deletion or cascade into a live quote. The link is provenance, not
    referential integrity: a broken one costs a bit of history, and enforcing
    it would cost a quote somebody is still delivering.
"""

from __future__ import annotations

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the interruption date, the renewal flag and its provenance."""
    op.add_column("quotes", sa.Column("interrupted_on", sa.Date(), nullable=True))
    op.add_column(
        "quotes",
        sa.Column(
            "auto_renew",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "quotes", sa.Column("renewed_from_id", sa.String(length=36), nullable=True)
    )
    # The server default did its job on the existing rows; dropping it now means
    # the application must state the flag on every insert, which is what the ORM
    # does. A default left in place is a default somebody eventually relies on
    # without noticing which value it is.
    with op.batch_alter_table("quotes") as batch:
        batch.alter_column("auto_renew", server_default=None)

    op.create_index("ix_quotes_auto_renew", "quotes", ["auto_renew", "valid_until"])


def downgrade() -> None:
    """Drop the three columns and the renewal index."""
    op.drop_index("ix_quotes_auto_renew", table_name="quotes")
    with op.batch_alter_table("quotes") as batch:
        batch.drop_column("renewed_from_id")
        batch.drop_column("auto_renew")
        batch.drop_column("interrupted_on")
