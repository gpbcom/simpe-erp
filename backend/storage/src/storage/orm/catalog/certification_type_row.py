from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Optional

# Third-party imports
from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class CertificationTypeRow(Base):
    """The ``certification_types`` table: the catalogue of qualifications.

    Attributes:
        id (str): UUID primary key.
        code (str): Short stable key; unique.
        label (str): Display name of the qualification.
        description (Optional[str]): Free-text description.
        is_active (bool): Whether it may still be required or recorded.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.

    Notes:
        - **No foreign key points at this table**, in either direction. An
          assistant's ``certifications.code`` and an intervention type's
          ``required_certification_codes`` both hold the *code*, not this row's
          identifier, and neither is constrained by the database. The reason is
          the JSON column: a requirement is a list, and a foreign key cannot
          reach inside one. Rather than have half the references enforced and
          half not, both are checked in the service on the way in, which also
          produces a 422 naming the unknown code instead of an integrity error
          naming a constraint.
        - Entries are retired with ``is_active``, never deleted, so the code an
          assistant's stored qualification names always resolves to something.
        - ``code`` is ``String(32)`` to match
          :attr:`~models.catalog.certification_type.CertificationType.CODE_MAX_LENGTH`.
          The two must agree: a model that accepts more than the column holds
          truncates silently on SQLite and errors on PostgreSQL, which is how
          the quote-status widening in migration 0006 was found.
    """

    __tablename__ = "certification_types"
    __table_args__ = (
        Index("ix_certification_types_code_unique", "code", unique=True),
        Index("ix_certification_types_is_active", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
