from __future__ import annotations

# Standard library imports
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

# Third-party imports
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class InterventionTypeRow(Base):
    """The ``intervention_types`` table.

    Attributes:
        id (str): UUID primary key.
        name (str): Display name; unique.
        code (str): Short stable key; unique.
        description (Optional[str]): Free-text description.
        service_category (str): ``necessity`` or ``comfort``.
        base_hourly_rate_ht (Optional[Decimal]): Rate for this type, or
            ``NULL`` to bill the agency default.
        is_active (bool): Whether the type may be put on a new quote.
        required_certification_codes (List[str]): Codes an assistant must hold
            to be given this work.
        required_skill_codes (List[str]): Codes an assistant must have declared
            to be given this work.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.

    Notes:
        The rate is ``Numeric(12, 3)`` rather than the two decimals a money
        amount uses. The contractual base rate is ``31.905`` €/h, so a rate
        column rounded to cents would silently change the price of every hour
        billed.

        ``NULL`` is meaningful here: it means "bill the agency default", not
        "free". Storing a copy of the default instead would freeze it, so
        changing the default would miss every type created before the change.

        Both ``name`` and ``code`` are unique. Two types with one name are
        indistinguishable on a quote, and a duplicated code breaks the stable
        reference exports rely on.

        ``required_certification_codes`` is a JSON array rather than a join
        table onto ``certification_types``. The matching column on a quote line
        must distinguish "no override" from "override to nothing", which a join
        table cannot express without a second flag column — and having one side
        of the same rule modelled relationally and the other not would be worse
        than having neither. The codes are validated against the catalogue in
        the service on the way in, which is also where an unknown one can be
        reported by name.

        ``required_skill_codes`` is a second column rather than more entries in
        the first. The planner reports the two as different unplaced reasons,
        and one merged array would make that distinction unrecoverable at the
        point it matters — a run that placed nothing has to say whether the fix
        is a hire or a profile somebody has not filled in.
    """

    __tablename__ = "intervention_types"
    __table_args__ = (
        Index("ix_intervention_types_name_unique", "name", unique=True),
        Index("ix_intervention_types_code_unique", "code", unique=True),
        Index("ix_intervention_types_is_active", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    service_category: Mapped[str] = mapped_column(String(16), nullable=False)
    base_hourly_rate_ht: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 3), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    required_certification_codes: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=list,
    )
    required_skill_codes: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
