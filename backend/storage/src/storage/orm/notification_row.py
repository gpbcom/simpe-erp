from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Optional

# Third-party imports
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class NotificationRow(Base):
    """The ``notifications`` table.

    Attributes:
        id (str): UUID primary key.
        recipient_id (str): The account it is addressed to.
        kind (str): What it is about.
        title (str): The one-line summary.
        body (Optional[str]): The detail.
        quote_id (Optional[str]): The quote it points at.
        is_read (bool): Whether the recipient has seen it.
        read_at (Optional[datetime]): When they marked it read.
        created_at (datetime): When the event happened.
        updated_at (datetime): Last-update timestamp.

    Notes:
        Deleted with its recipient: a notification addressed to an account that
        no longer exists is unreachable, and keeping it would leave rows nothing
        can ever read or clear.

        ``quote_id`` carries **no** foreign key, deliberately. The notification
        is the record that somebody was told something, and it must survive the
        quote being deleted — otherwise cancelling a quote would erase the
        evidence that a manager had been asked to approve it.

        ``(recipient_id, is_read, created_at)`` is the index that matters: every
        read is "my unread notifications, newest first", and the badge count is
        the same query.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "ix_notifications_recipient_unread",
            "recipient_id",
            "is_read",
            "created_at",
        ),
        Index("ix_notifications_quote", "quote_id"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    recipient_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quote_id: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
