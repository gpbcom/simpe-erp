from __future__ import annotations

# Standard library imports
from datetime import datetime

# Third-party imports
from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class TeamMemberRow(Base):
    """The ``team_members`` table: who is on which team.

    Attributes:
        id (str): UUID primary key.
        team_id (str): The team.
        member_kind (str): ``user`` or ``hca``.
        member_id (str): The account or the assistant record.
        created_at (datetime): When the person joined the team.

    Notes:
        - Polymorphic on ``member_kind`` and therefore carrying **no foreign key
          on ``member_id``**, exactly like
          :class:`~storage.orm.organisation.agency_member_row.AgencyMemberRow`.
          The service validates the target and detaches it on deletion.
        - ``uq_team_members_member`` — **a person is on at most one team** — is
          the load-bearing constraint of the whole feature. Plannings are
          computed per team and stored with a per-team delete, so somebody on
          two teams would have two complete calendars written for the same week
          by two runs, neither of which clears the other's visits. They would be
          double-booked, and nothing anywhere would report it.
        - There is no ``is_manager`` column. See
          :class:`~storage.orm.organisation.team_row.TeamRow` for why the
          manager is a required column on the team instead.
    """

    __tablename__ = "team_members"
    __table_args__ = (
        Index("ix_team_members_team", "team_id"),
        Index("uq_team_members_member", "member_kind", "member_id", unique=True),  # noqa: E501
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    team_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    member_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    member_id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)  # noqa: E501
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
