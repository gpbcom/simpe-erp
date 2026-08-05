from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import TYPE_CHECKING, Optional

# Third-party imports
from sqlalchemy import Date, ForeignKey, Index, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

# First-party imports
from storage.orm.base import Base

if TYPE_CHECKING:
    # First-party imports
    from storage.orm.hca_row import HcaRow


class AvailabilityRow(Base):
    """The ``availability_slots`` table.

    Attributes:
        id (str): UUID primary key.
        hca_id (str): The assistant the absence belongs to.
        start_date (date): First day of the period, inclusive.
        end_date (date): Last day of the period, inclusive.
        kind (str): Why the assistant is unavailable.
        start_time (Optional[time]): Start of the blocked window, or ``None``.
        end_time (Optional[time]): End of the blocked window, or ``None``.
        note (Optional[str]): Free-text note.
        hca (HcaRow): The owning assistant.

    Notes:
        The composite index on ``(hca_id, start_date, end_date)`` is the one
        the planner uses: every solve asks which absences overlap the planning
        window, for every assistant.
    """

    __tablename__ = "availability_slots"
    __table_args__ = (
        Index("ix_availability_hca_period", "hca_id", "start_date", "end_date"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    hca_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("hcas.id", ondelete="CASCADE"),
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    end_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    hca: Mapped[HcaRow] = relationship(back_populates="availability")
