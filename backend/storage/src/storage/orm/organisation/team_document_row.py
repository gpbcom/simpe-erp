from __future__ import annotations

# Standard library imports
from datetime import datetime

# Third-party imports
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class TeamDocumentRow(Base):
    """The ``team_documents`` table: one file in a team's shared space.

    Attributes:
        id (str): UUID primary key.
        team_id (str): The team whose space the file sits in.
        company_id (str): The company that team belongs to.
        file_name (str): What the uploader called it.
        content_type (str): The media type the object store detected.
        size_bytes (int): How large the stored object is.
        document_key (str): Where the object lives in the store.
        uploaded_by (str): The account that added it.
        uploaded_by_name (str): That account's name at the time.
        created_at (datetime): When it was added.
        updated_at (datetime): Last-update timestamp.

    Notes:
        - The **key** is stored, never a URL — the invoice's shape rather than
          the portrait's. A team's documents are the agency's private paperwork,
          and a public URL would make them readable for ever by anybody who was
          sent one, whatever the application later decided about permissions.
        - ``uploaded_by`` carries **no foreign key**, and the uploader's name is
          copied beside it. A file added by somebody who has since left still
          has to say who added it, and a join through a deleted account would
          print nothing.
        - The index is on ``(team_id, created_at)`` rather than ``team_id``
          alone, because the only read is "this team's files, newest first".
        - ``updated_at`` is carried even though a document is never edited —
          replacing a file means uploading a new one and removing the old,
          because the object in the store is immutable once written. The column
          is here for uniformity with every other table, which is what lets the
          shared mapper machinery stamp this row like any other rather than
          needing a special case that somebody has to remember exists.
    """

    __tablename__ = "team_documents"
    __table_args__ = (Index("ix_team_documents_team", "team_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    team_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    document_key: Mapped[str] = mapped_column(String(512), nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)
    uploaded_by_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
