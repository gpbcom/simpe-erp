from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Optional

# Third-party imports
from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class EInvoicingIntegrationRow(Base):
    """The ``einvoicing_integrations`` table.

    Attributes:
        id (str): Primary key.
        company_id (str): The agency this belongs to.
        provider (str): The certified platform.
        enabled (bool): Whether invoices are transmitted through it.
        credential_ciphertext (str): The encrypted credentials.
        credential_hint (str): The masked tail of the key, for the screen.
        last_checked_at (Optional[datetime]): When the key was last proven.
        last_check_error (Optional[str]): Why the last check failed, if it did.
        updated_by (Optional[str]): The account that last changed it.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.

    Notes:
        - **One row per agency per platform**, and the unique constraint says
          so. An agency holding two rows for the same platform would have two
          keys and no way to say which one an invoice went out under.
        - **The ciphertext is ``Text`` rather than a sized string.** Fernet
          output grows with the payload and the payload grows when a platform
          wants extra references. A column sized to today's four fields would
          fail on the day a fifth was added, in production, on a save.
        - There is a partial index on the enabled row rather than a unique
          constraint over ``(company_id, enabled)``: only one row per agency may
          be enabled, but *many* may be disabled, and a plain unique constraint
          cannot express that. Enforcing it in the index means two concurrent
          enables cannot both win, whatever the application does.
        - ``updated_by`` is not a foreign key to ``users``, for the same reason
          the billing settings' is not: an audit trail that disappears when the
          account is deleted is not an audit trail.
    """

    __tablename__ = "einvoicing_integrations"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "provider", name="uq_einvoicing_company_provider"
        ),
        # **The one-active rule, enforced where the application cannot lose
        # it.** A plain unique constraint over (company_id, enabled) would also
        # forbid an agency from holding two *disabled* platforms, which is the
        # ordinary state of an agency that has tried one and moved on. A
        # partial index constrains only the enabled rows. Declared for both
        # dialects because the suite runs on SQLite and deployments on
        # PostgreSQL, and an invariant that holds in only one of them is an
        # invariant the tests cannot prove.
        Index(
            "uq_einvoicing_one_enabled_per_company",
            "company_id",
            unique=True,
            postgresql_where=text("enabled"),
            sqlite_where=text("enabled"),
        ),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credential_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    credential_hint: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_check_error: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
