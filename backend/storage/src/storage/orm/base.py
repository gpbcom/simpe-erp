from __future__ import annotations

# Standard library imports
from decimal import Decimal
from typing import ClassVar, Dict

# Third-party imports
from sqlalchemy import JSON, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeEngine


class Base(DeclarativeBase):
    """Declarative base shared by every ORM table in the backend.

    Attributes:
        ID_LENGTH (ClassVar[int]): Width of every identifier column. Sized for
            a canonical UUID string.
        type_annotation_map (ClassVar[Dict[type, TypeEngine]]): Per-type column
            defaults applied to annotated columns.

    Notes:
        - ``JSON`` is declared with a PostgreSQL variant so it becomes ``JSONB``
          against the real database while staying plain ``JSON`` on SQLite. The
          repository tests run on an in-memory SQLite engine to stay fast and
          hermetic; without the variant the metadata would not create there at
          all, and the tests would need a live PostgreSQL instance.
        - Identifiers are stored as strings rather than as native UUIDs. The
          domain models type them as ``Optional[str]``, and keeping the column
          type aligned means the mappers never convert on the way in or out.
        - ``Decimal`` maps to ``Numeric(12, 2)`` by default — the shape of a
          money amount. Columns that hold a rate rather than an amount override
          it with three decimals, because the base hourly rate is ``31.905``.
    """

    ID_LENGTH: ClassVar[int] = 36

    type_annotation_map: ClassVar[Dict[type, TypeEngine]] = {
        str: String(255),
        Decimal: Numeric(12, 2),
        dict: JSON().with_variant(JSONB(), "postgresql"),
    }
