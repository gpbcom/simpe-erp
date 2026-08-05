"""Per-recipient notifications.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-05

Notes:
    One row per recipient, not one row per event: a quote submitted to an agency
    with three managers writes three rows. Read state belongs to a person, and
    two managers must be able to disagree about whether they have dealt with
    something — which a single shared row cannot express.

    ``recipient_id`` cascades from ``users``: a notification addressed to an
    account that no longer exists is unreachable, and keeping it would leave
    rows nothing can read or clear.

    ``quote_id`` deliberately carries **no** foreign key. The notification
    records that somebody was told something, and it has to survive the quote
    being deleted — otherwise cancelling a quote would erase the evidence that a
    manager was asked to approve it.
"""

from __future__ import annotations

# Standard library imports
from typing import Sequence, Union

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the notifications table and its two indexes."""
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "recipient_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("quote_id", sa.String(36), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Every read is "my unread notifications, newest first", and the badge count
    # is the same query with a different projection.
    op.create_index(
        "ix_notifications_recipient_unread",
        "notifications",
        ["recipient_id", "is_read", "created_at"],
    )
    op.create_index("ix_notifications_quote", "notifications", ["quote_id"])


def downgrade() -> None:
    """Drop the notifications table."""
    op.drop_index("ix_notifications_quote", table_name="notifications")
    op.drop_index("ix_notifications_recipient_unread", table_name="notifications")
    op.drop_table("notifications")
