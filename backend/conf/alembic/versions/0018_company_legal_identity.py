"""Record the agency's legal identity, for the documents that must carry it.

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-07

Notes:
    A quote sent to a customer is a commercial offer, and French law is
    specific about what one has to say about whoever is making it: the legal
    form, the share capital where there is one, the trade-register entry and
    the intra-community VAT number, alongside the trading name and address the
    table already held.

    None of that was stored. The quote workbook could name the agency and
    nothing else, which made it a document a recipient had no way to verify
    and no way to reply to.

    **Every column is nullable, and that is deliberate.** There is no safe
    value to invent for any of them. A share capital backfilled to zero would
    be a false declaration. An RCS entry backfilled to the SIRET would be a
    wrong one. An agency that has not filled these in yet simply prints
    without them — the document joins only the parts that are set — and the
    administrator's own screen is where they get filled in.

    That is the opposite of the choice migrations 0012, 0013 and 0015 made,
    and for the opposite reason: those columns had a correct answer for every
    existing row, and these have none.
"""

from __future__ import annotations

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

#: Name, type. Widths match the model's own limits, and the numeric scale is
#: two because a share capital is an amount of euros and cents.
COLUMNS = (
    ("legal_form", sa.String(length=64)),
    ("share_capital", sa.Numeric(precision=14, scale=2)),
    ("rcs_number", sa.String(length=64)),
    ("vat_number", sa.String(length=20)),
    ("phone_number", sa.String(length=64)),
)


def upgrade() -> None:
    """Add the five legal-identity columns to the agencies table."""
    for name, column_type in COLUMNS:
        op.add_column("companies", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    """Drop the legal-identity columns.

    Notes:
        This loses whatever each agency declared about itself, and there is
        nowhere to put it — no earlier column holds a legal form or a VAT
        number. The quotes go back to naming the agency by trading name alone,
        which is the state this revision exists to leave behind.
    """
    for name, _ in reversed(COLUMNS):
        op.drop_column("companies", name)
