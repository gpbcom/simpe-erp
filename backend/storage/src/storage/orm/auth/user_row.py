from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Optional

# Third-party imports
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class UserRow(Base):
    """The ``users`` table.

    Attributes:
        id (str): UUID primary key.
        email (str): Sign-in address; unique, stored lower-cased.
        first_name (str): Given name; empty for a mononym.
        last_name (str): Family name, or the whole name of a mononym.
        hashed_password (Optional[str]): Bcrypt hash, when a password is set.
        role (str): ``hca``, ``manager`` or ``admin``.
        is_active (bool): Whether sign-in is permitted.
        customer_id (Optional[str]): The customer record a customer account
            belongs to.
        hca_id (Optional[str]): The assistant record an assistant account
            belongs to.
        company_id (str): The company this account belongs to.
        account_origin (str): ``self-registered`` or ``created-by-staff``.
        photo_url (Optional[str]): Object-store URL of the holder's portrait.
        language (str): ``fr`` or ``en``; the language this holder reads the
            application, and the documents it emails them, in.
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
        Index("ix_users_customer_id", "customer_id"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    # Two columns rather than one display name, since ``User`` became a
    # ``Person``. ``first_name`` is nullable-in-spirit — it is NOT NULL but may
    # be the empty string — because a mononym or a service account has no given
    # name and the whole value lands in ``last_name``. Migration 0014 split the
    # old ``full_name`` column on its first space, which round-trips exactly.
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hca_id: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("hcas.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # ``RESTRICT`` like ``hca_id``, and for the same reason: the database must
    # not leave an account pointing at a household that no longer exists.
    # ``CustomerService.delete`` removes the portal account in the same
    # transaction, so the constraint never fires in practice — it is there for
    # the path somebody adds later and forgets.
    customer_id: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # NOT NULL: every account belongs to exactly one agency. The column
    # was nullable while companies were newer than the rows that point at
    # them; migration 0008 backfilled the stragglers and closed it, so no
    # row can go back to belonging to nobody.
    company_id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)
    account_origin: Mapped[str] = mapped_column(
        String(24), nullable=False, default="self-registered"
    )
    # Text rather than a bounded string, like the assistant's: the object key
    # carries a generated component, and a bucket moved behind a CDN can make
    # the public prefix longer than whatever limit looked generous today.
    photo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
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
