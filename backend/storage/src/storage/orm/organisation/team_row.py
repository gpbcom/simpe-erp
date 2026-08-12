from __future__ import annotations

# Standard library imports
from datetime import datetime

# Third-party imports
from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class TeamRow(Base):
    """The ``teams`` table: people at one site, under one manager.

    Attributes:
        id (str): UUID primary key.
        company_id (str): The company the team belongs to.
        agency_id (str): The site it works from.
        name (str): What the team is called.
        manager_user_id (str): The account that runs it.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.

    Notes:
        - ``manager_user_id`` is **NOT NULL with a restricting foreign key**,
          and that is the whole expression of "exactly one manager". A flag on
          ``team_members`` could be set on nobody or on five, and pinning it to
          one would need a partial unique index *plus* something proving at
          least one exists — which no database states without a trigger. The
          ``RESTRICT`` is the other half: an account that still runs a team
          cannot be deleted out from under it.
        - ``company_id`` is carried here as well as on the site, and the
          duplication is deliberate. Every planning query filters on the company
          first, and reaching it through a join to ``agencies`` would put a
          second table in the most heavily read statement in the application.
        - The foreign key to ``agencies`` is ``RESTRICT``: deleting a site would
          otherwise silently take its teams, their plannings and their quotes'
          only route to a workforce.
    """

    __tablename__ = "teams"
    __table_args__ = (
        Index("ix_teams_company", "company_id"),
        Index("ix_teams_agency", "agency_id"),
        Index("ix_teams_manager", "manager_user_id"),
        Index("uq_teams_company_name", "company_id", "name", unique=True),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    agency_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("agencies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    manager_user_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
