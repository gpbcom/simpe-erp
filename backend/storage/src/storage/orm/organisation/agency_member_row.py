from __future__ import annotations

# Standard library imports
from datetime import datetime

# Third-party imports
from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class AgencyMemberRow(Base):
    """The ``agency_members`` table: who works at which site.

    Attributes:
        id (str): UUID primary key.
        agency_id (str): The site.
        member_kind (str): ``user`` or ``hca``.
        member_id (str): The account or the assistant record.
        created_at (datetime): When the person joined the site.

    Notes:
        - **There is deliberately no foreign key on ``member_id``.** It points
          at two different tables depending on ``member_kind``, which no
          declarative constraint can express. The alternative — one join table
          per kind — would have doubled every membership query and every
          teardown for a distinction the two never actually make. The service is
          what validates the target exists, and it is also what detaches a
          person when their record is deleted, because nothing here cascades.
        - ``uq_agency_members_member`` is what makes "everybody belongs to
          exactly one site" true. Moving somebody is therefore a deliberate
          two-step rather than an accident of an insert.
        - The foreign key to ``agencies`` **does** cascade: a membership row
          means nothing without the site it points at.
    """

    __tablename__ = "agency_members"
    __table_args__ = (
        Index("ix_agency_members_agency", "agency_id"),
        Index("uq_agency_members_member", "member_kind", "member_id", unique=True),  # noqa: E501
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    agency_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
    )
    member_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    member_id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)  # noqa: E501
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
