from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Optional

# Third-party imports
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class UserRow(Base):
    """The ``users`` table.

    Attributes:
        id (str): UUID primary key.
        email (str): Sign-in address; unique, stored lower-cased.
        full_name (str): Display name.
        hashed_password (Optional[str]): Bcrypt hash, when a password is set.
        role (str): ``hca``, ``manager`` or ``admin``.
        is_active (bool): Whether sign-in is permitted.
        hca_id (Optional[str]): The assistant record an assistant account
            belongs to.
        company_id (Optional[str]): The company this account belongs to.
        account_origin (str): ``self-registered`` or ``created-by-staff``.
        must_change_password (bool): Whether the temporary password must
            still be replaced before the account can be used.
        password_changed_at (Optional[datetime]): When the holder last
            chose their own password.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.

    Notes:
        - ``email`` carries a unique index. The domain model lower-cases the
          address before it reaches here, so the constraint cannot be defeated by
          changing capitalisation.
        - ``hca_id`` is a real foreign key with ``ON DELETE RESTRICT``. Deleting
          an assistant while an account still points at it would leave that
          account unable to resolve its own planning — the database refuses
          rather than letting the dangling link happen.
    """

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_email_unique", "email", unique=True),
        Index("ix_users_role", "role"),
        Index("ix_users_hca_id", "hca_id"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hca_id: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("hcas.id", ondelete="RESTRICT"),
        nullable=True,
    )
    company_id: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
    account_origin: Mapped[str] = mapped_column(
        String(24), nullable=False, default="self-registered"
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
