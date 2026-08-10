"""Record where the agency is paid and what its letterhead looks like.

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-10

Notes:
    Two things the agency's own record could not hold. An **IBAN and BIC**, so
    a customer knows where to send the money — a quote that states a price and
    no account is an offer nobody can act on. And a **logo**, because the
    document that carries the agency's legal identity should also look like it
    came from them.

    Only the logo's *URL* is stored. The image itself goes into the object
    store, beside the assistant photographs, under its own key prefix.

    The IBAN column is plain text, like every other column in this schema.
    What limits who can read it is the response model the agency routes return
    — an administrator reads it whole, everybody else reads it masked — not
    the storage. Encrypting it here would protect nothing the database's own
    access control does not already, while making the one caller entitled to
    read it back unable to correct a typo.

    Nullable, for the same reason migration 0018 gave: there is no safe value
    to invent. An agency that has not filled its bank details in prints a quote
    without them, which is what it did before this revision existed.
"""

from __future__ import annotations

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

#: Name, type. Widths match the model's own limits: 34 is the longest IBAN any
#: country issues, a BIC is eight or eleven characters, and 512 leaves room for
#: an object-store URL carrying a bucket, a prefix and a generated key.
COLUMNS = (
    ("iban", sa.String(length=34)),
    ("bic", sa.String(length=11)),
    ("logo_url", sa.String(length=512)),
)


def upgrade() -> None:
    """Add the banking and logo columns to the agencies table."""
    for name, column_type in COLUMNS:
        op.add_column("companies", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    """Drop the banking and logo columns.

    Notes:
        This loses each agency's bank details, and the link to its logo. The
        logo objects themselves stay in the bucket — a schema migration has no
        business reaching into an object store, and an orphaned image costs
        pennies where a deleted one cannot be recovered.
    """
    for name, _ in reversed(COLUMNS):
        op.drop_column("companies", name)
