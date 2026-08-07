from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Optional

# Third-party imports
from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class SkillTypeRow(Base):
    """The ``skill_types`` table: the catalogue of skills.

    Attributes:
        id (str): UUID primary key.
        code (str): Short stable key; unique.
        label (str): Display name of the skill.
        description (Optional[str]): Free-text description.
        is_active (bool): Whether it may still be required or declared.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.

    Notes:
        - **No foreign key points at this table**, in either direction, for
          exactly the reasons set out on
          :class:`~storage.orm.catalog.certification_type_row.CertificationTypeRow`:
          an assistant's ``skills.code`` and an intervention type's
          ``required_skill_codes`` both hold the *code*, and a foreign key
          cannot reach inside a JSON array. Both are checked in the service on
          the way in, which also produces a 422 naming the unknown code instead
          of an integrity error naming a constraint.
        - Entries are retired with ``is_active``, never deleted, so the code an
          assistant's declared skill names always resolves to something.
        - ``code`` is ``String(32)`` to match
          :attr:`~models.catalog.skill_type.SkillType.CODE_MAX_LENGTH`. The two
          must agree: a model that accepts more than the column holds truncates
          silently on SQLite and errors on PostgreSQL.
        - A separate table from ``certification_types`` rather than a ``kind``
          column on one shared table. The two are edited by different people
          under different permissions and are required independently, so one
          table would need every query in both catalogues to remember the
          filter — and the one that forgot would let an assistant declare
          themselves a diploma.
    """

    __tablename__ = "skill_types"
    __table_args__ = (
        Index("ix_skill_types_code_unique", "code", unique=True),
        Index("ix_skill_types_is_active", "is_active"),
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
