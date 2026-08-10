from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from typing import Optional

# Third-party imports
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class PlanningRunRow(Base):
    """The ``planning_runs`` table.

    Attributes:
        id (str): UUID primary key.
        status (str): Where the run is.
        company_id (str): The agency whose calendar this run rewrites.
        requested_by (str): The administrator who started it.
        period_start (date): First day planned, inclusive.
        period_end (date): Last day planned, inclusive.
        started_at (Optional[datetime]): When the solver began.
        finished_at (Optional[datetime]): When it stopped.
        total_travel_minutes (Optional[int]): Travel in the solution.
        scheduled_count (Optional[int]): How many requirements were placed.
        is_optimised (Optional[bool]): Whether the travel was proved
            minimal. Null for a run that predates the two-pass solve.
        unplaced_quotes (Optional[list]): The report an operator reads, one
            entry per quote whose work could not all be fitted. Stored so the
            screen never has to re-run the diagnosis to say what went wrong.
        unassigned_requirement_ids (Optional[str]): Comma-separated ids that
            could not be placed.
        error_message (Optional[str]): Why the run failed, when it did.

    Notes:
        - ``requested_by`` carries no foreign key. It is an audit trail, and an
          administrator leaving the agency must not take the record of which
          plannings they ran with them — nor block their account being deleted.
        - ``company_id`` is stored rather than derived through ``requested_by``
          for exactly that reason: the requester is allowed to vanish, and the
          agency a run belongs to must not vanish with them. It is what scopes
        - the work the run schedules and the calendar it rewrites.
          The unassigned ids are a delimited string rather than a table. They are
          only ever read back whole, alongside the run, and a table would add a
          join to serve a list nothing queries into.
    """

    __tablename__ = "planning_runs"
    __table_args__ = (
        Index("ix_planning_runs_status", "status"),
        Index("ix_planning_runs_period", "period_start", "period_end"),
        Index("ix_planning_runs_company", "company_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    company_id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_travel_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    scheduled_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Nullable, and null is not false: a run from before the two-pass
    # solve existed never answered the question, and rendering it as
    # "not optimised" would invent a finding about a historic plan.
    is_optimised: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    unassigned_requirement_ids: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    # JSON rather than a joined string, unlike the ids above. What is stored
    # here is a nested structure — a quote, its customer, and a visit with a
    # reason each — and flattening that into text would mean parsing it back
    # with a format nobody wrote down.
    unplaced_quotes: Mapped[Optional[list]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
