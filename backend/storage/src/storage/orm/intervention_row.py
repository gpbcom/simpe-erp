from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import Optional

# Third-party imports
from sqlalchemy import Date, Float, ForeignKey, Index, String, Time
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class InterventionRow(Base):
    """The ``interventions`` table.

    Attributes:
        id (str): UUID primary key.
        planning_run_id (str): The run that produced this visit.
        name (str): What the service is.
        intervention_type_id (str): The catalog entry it sells.
        quote_line_id (str): The accepted quote line it delivers.
        hca_id (str): The assistant who performs it.
        hca_full_name (str): Their name, copied when the visit was planned.
        customer_id (str): The customer it is for.
        day (date): The day it happens.
        start_time (time): When it begins.
        end_time (time): When it ends.
        street (str): Street line of where it happens.
        postal_code (str): Postal code of where it happens.
        city (str): City of where it happens.
        country (str): Country of where it happens.
        latitude (Optional[float]): Resolved latitude, when geocoded.
        longitude (Optional[float]): Resolved longitude, when geocoded.
        geocoding_error (Optional[str]): Stable geocoding failure code.
        status (str): Where the visit is in its lifecycle.

    Notes:
        The assistant's name and the customer's address are **copies**, not
        joins. A planning is a document an assistant works from; re-resolving
        it against live records would make a printed round disagree with the
        screen after any edit.

        Deleted with its run: re-planning a period replaces the whole plan for
        it, so a visit outliving its run would be a ghost nothing produced.

        ``(hca_id, day)`` is the index that matters — it serves both an
        assistant's own diary and the manager's whole-workforce view.
    """

    __tablename__ = "interventions"
    __table_args__ = (
        Index("ix_interventions_hca_day", "hca_id", "day"),
        Index("ix_interventions_run", "planning_run_id"),
        Index("ix_interventions_day", "day"),
        Index("ix_interventions_customer", "customer_id"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    planning_run_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("planning_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    intervention_type_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH), nullable=False
    )
    quote_line_id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)
    hca_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("hcas.id", ondelete="CASCADE"),
        nullable=False,
    )
    hca_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    street: Mapped[str] = mapped_column(String(255), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(16), nullable=False)
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(128), nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    geocoding_error: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
