"""Give every account a portrait, not only the ones bound to an assistant.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-07

Notes:
    One nullable ``photo_url`` column on ``users``, mirroring the one ``hcas``
    has carried since 0001.

    It is a **second** column rather than a move, because the two answer
    different questions. The assistant's portrait is their pin on the manager's
    map, and it belongs to the person a manager schedules. This one belongs to
    the credential, and every signed-in account has one — including the managers
    and administrators who have no assistant record at all and therefore had
    nowhere to put a face.

    ``Text`` rather than a bounded string, like the assistant's. The object key
    carries a generated component, and a bucket later placed behind a CDN can
    make the public prefix longer than whatever limit looked generous today.

    Nothing is backfilled. An account bound to an assistant record could have
    the assistant's portrait copied across, but the two are written together
    from now on — copying here would only paper over the rows nobody has
    re-saved, and a half-populated column reads as "some people chose not to
    upload one".
"""

from __future__ import annotations

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the account portrait column."""
    op.add_column("users", sa.Column("photo_url", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop the account portrait column."""
    with op.batch_alter_table("users") as batch:
        batch.drop_column("photo_url")
