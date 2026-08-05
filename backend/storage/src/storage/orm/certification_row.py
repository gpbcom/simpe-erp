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
    from storage.orm.hca_row import HcaRow


class CertificationRow(Base):
    """The ``certifications`` table.

    Attributes:
        id (str): UUID primary key.
        hca_id (str): The assistant holding the qualification.
        name (str): Name of the qualification.
        issuer (Optional[str]): Body that awarded it.
        obtained_on (Optional[date]): Date it was awarded.
        expires_on (Optional[date]): Date it lapses.
        hca (HcaRow): The owning assistant.

    Notes:
        Deleted with its assistant: a qualification has no meaning without the
        person who holds it.
    """

    __tablename__ = "certifications"
    __table_args__ = (Index("ix_certifications_hca_id", "hca_id"),)

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    hca_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("hcas.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    obtained_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expires_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    hca: Mapped[HcaRow] = relationship(back_populates="certifications")
