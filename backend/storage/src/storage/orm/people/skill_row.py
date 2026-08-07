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


class SkillRow(Base):
    """The ``skills`` table.

    Attributes:
        id (str): UUID primary key.
        hca_id (str): The assistant who declared the skill.
        name (str): Name of the skill.
        code (Optional[str]): The catalogue entry this instantiates, when it
            was picked from the catalogue rather than typed.
        issuer (Optional[str]): Who attested it.
        obtained_on (Optional[date]): Date it was acquired.
        expires_on (Optional[date]): Date it lapses.
        hca (HcaRow): The owning assistant.

    Notes:
        - Deleted with its assistant: a skill has no meaning without the person
          who declared it.
        - ``code`` is nullable and carries **no foreign key** to
          ``skill_types``, for the same reason the certification link has none:
          an assistant may declare something the catalogue has no name for yet,
          and the matching side — an intervention type's list of required codes
          — cannot be constrained anyway. Both are checked in the service.
        - Indexed on ``code`` because the planner filters on it: the skill
          constraint asks "who has declared LEVE-PERSONNE?" once per
          requirement that needs one.
        - **Its ``id`` is addressed by callers, unlike a certification's.** A
          skill is deleted one at a time — by its owner, a manager or an
          administrator — so the primary key travels to the client and comes
          back in a URL. That is why
          :class:`~models.people.hca.skill.Skill` carries an ``id`` where
          :class:`~models.people.hca.certification.Certification` does not.
    """

    __tablename__ = "skills"
    __table_args__ = (
        Index("ix_skills_hca_id", "hca_id"),
        Index("ix_skills_code", "code"),
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

    hca: Mapped[HcaRow] = relationship(back_populates="skills")
