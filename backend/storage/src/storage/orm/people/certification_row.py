from __future__ import annotations

# Standard library imports
from datetime import date
from typing import TYPE_CHECKING, Optional

# Third-party imports
from sqlalchemy import Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

# First-party imports
from storage.orm.base import Base

if TYPE_CHECKING:
    # First-party imports
    from storage.orm.people.hca_row import HcaRow


class CertificationRow(Base):
    """The ``certifications`` table.

    Attributes:
        id (str): UUID primary key.
        hca_id (str): The assistant holding the qualification.
        name (str): Name of the qualification.
        code (Optional[str]): The catalogue entry this instantiates, when it
            was picked from the catalogue rather than typed.
        issuer (Optional[str]): Body that awarded it.
        obtained_on (Optional[date]): Date it was awarded.
        expires_on (Optional[date]): Date it lapses.
        hca (HcaRow): The owning assistant.

    Notes:
        - Deleted with its assistant: a qualification has no meaning without
          the person who holds it.
        - ``code`` is nullable and carries **no foreign key** to
          ``certification_types``. The catalogue arrived after the records did,
          so a qualification typed before it existed has no code and is still
          somebody's qualification. And the matching side of the pair — an
          intervention type's list of required codes — cannot be constrained
          anyway. Both are checked in the service instead, where an unknown
          code produces a message naming it.
        - Indexed because the planner filters on it: the certification
          constraint asks "who holds DEAES?" once per requirement that needs
          one.
    """

    __tablename__ = "certifications"
    __table_args__ = (
        Index("ix_certifications_hca_id", "hca_id"),
        Index("ix_certifications_code", "code"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    hca_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("hcas.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    issuer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    obtained_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expires_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    hca: Mapped[HcaRow] = relationship(back_populates="certifications")
