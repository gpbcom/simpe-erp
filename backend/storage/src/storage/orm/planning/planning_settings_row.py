from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Optional

# Third-party imports
from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class PlanningSettingsRow(Base):
    """The ``planning_settings`` table.

    Attributes:
        id (str): Primary key; always the singleton identifier.
        max_intervention_radius_km (float): How far from home an assistant may
            be sent.
        day_start_minute (int): Earliest start minute of the working day.
        day_end_minute (int): Latest end minute of the working day.
        lunch_break_minutes (int): Length of the uninterrupted midday break.
        lunch_window_start_minute (int): Earliest minute the break may start.
        lunch_window_end_minute (int): Latest minute the break may end.
        updated_by (Optional[str]): The account that last changed these.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.

    Notes:
        One row, with a fixed textual primary key rather than a UUID. These are
        agency-wide rules; a table that can hold two of them raises the
        question of which the solver read, and the answer would depend on
        insertion order.

        ``updated_by`` is deliberately not a foreign key to ``users``. It is an
        audit trail, and an audit trail that disappears when the account is
        deleted is not one — the question "who halved the radius?" outlives the
        person who left.
    """

    __tablename__ = "planning_settings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    max_intervention_radius_km: Mapped[float] = mapped_column(Float, nullable=False)
    # Minutes from midnight, not a TIME column. This is the unit the solver
    # works in, and storing a TIME would mean converting on every read of a
    # value that is never displayed as a clock time except in one report.
    day_start_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    day_end_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    lunch_break_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    lunch_window_start_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    lunch_window_end_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
