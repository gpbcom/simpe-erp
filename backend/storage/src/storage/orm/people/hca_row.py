from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

# Third-party imports
from sqlalchemy import Boolean, DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

# First-party imports
from storage.orm.base import Base

if TYPE_CHECKING:
    # First-party imports
    from storage.orm.people.availability_row import AvailabilityRow
    from storage.orm.people.certification_row import CertificationRow
    from storage.orm.people.skill_row import SkillRow


class HcaRow(Base):
    """The ``hcas`` table.

    Attributes:
        id (str): UUID primary key.
        first_name (str): Given name.
        last_name (str): Family name.
        phone_number (str): Contact telephone number, canonical form.
        email (str): Contact email address.
        street (str): Street line of the home address.
        postal_code (str): Postal code of the home address.
        city (str): City of the home address.
        country (str): Country of the home address.
        latitude (Optional[float]): Resolved latitude, when geocoded.
        longitude (Optional[float]): Resolved longitude, when geocoded.
        geocoding_error (Optional[str]): Stable code for a geocoding failure.
        contract_type (str): ``cdi``, ``cdd``, ``interim`` or ``internship``.
        driving_license_categories (Optional[str]): Comma-separated licence
            categories, or ``None`` when no licence is held.
        driving_license_number (Optional[str]): Licence number.
        driving_license_obtained_on (Optional[datetime]): Licence issue date.
        driving_license_expires_on (Optional[datetime]): Licence renewal date.
        photo_url (Optional[str]): Portrait URL.
        field_employee (bool): Whether this person may be placed on an
            intervention planning.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.
        certifications (List[CertificationRow]): Qualifications held.
        skills (List[SkillRow]): Skills the assistant declared.
        availability (List[AvailabilityRow]): Recorded absences.
        working_weekdays (str): The days of the week worked, comma-separated
            and ordered Monday first.

    Notes:
        - The licence is flattened into four nullable columns rather than given
          its own table. It is strictly one-per-assistant, so a table would add a
          join for no gain; ``driving_license_categories`` being ``NULL`` is what
          distinguishes "no licence" from "a licence with no category recorded".
        - Certifications, skills and availability *are* separate tables: all
          three are one-to-many, and availability is queried by date range on
          every solve.
        - ``skills`` is a third child rather than more rows in
          ``certifications`` with a discriminator. The two are written by
          different people through different routes — a manager replaces the
          certification list wholesale, an assistant appends one skill at a
          time — and one table would mean the employment form's wholesale
          replacement silently deleting every skill its owner had declared.
        - Every child cascades on delete. An orphaned absence would silently
          block scheduling for an assistant who no longer exists.
        - ``field_employee`` is ``NOT NULL`` with no nullable phase. Migration
          0012 adds it with a server default of true and drops the default
          afterwards, so every row that existed before it did reads back as
          schedulable — which is what those rows already were. A nullable
          column would have left the planner deciding what ``NULL`` meant, and
          the two possible answers are "everybody works" and "nobody does".
        - It is indexed because every solve filters on it, and the filter runs
          before anything else the planner does.
        - ``working_weekdays`` is one delimited column, not a child table and
          not a bitmask. It is always read whole and never queried by day, so a
          table would be seven rows per assistant for no gain; a bitmask would
          be four bytes nobody can read in a ``psql`` session. The whole week
          spelled out is 62 characters, so ``String(80)`` has room to spare.
        - It is ``NOT NULL`` for the same reason ``field_employee`` is, and
          migration 0013 backfills it the same way: with the *seven-day* week,
          not the standard one. Every row that existed before the column did
          was schedulable on any day, and narrowing them to Monday-to-Friday
          would have cancelled weekend rounds nobody asked to cancel.
    """

    __tablename__ = "hcas"
    __table_args__ = (
        Index("ix_hcas_last_name", "last_name"),
        Index("ix_hcas_contract_type", "contract_type"),
        Index("ix_hcas_field_employee", "field_employee"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[str] = mapped_column(String(128), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    street: Mapped[str] = mapped_column(String(255), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(16), nullable=False)
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(128), nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    geocoding_error: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # noqa: E501
    company_id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), nullable=False)  # noqa: E501
    contract_type: Mapped[str] = mapped_column(String(16), nullable=False)
    driving_license_categories: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    driving_license_number: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    driving_license_obtained_on: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    driving_license_expires_on: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    photo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    working_weekdays: Mapped[str] = mapped_column(String(80), nullable=False)
    field_employee: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # noqa: E501
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    certifications: Mapped[List[CertificationRow]] = relationship(
        back_populates="hca",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    skills: Mapped[List[SkillRow]] = relationship(
        back_populates="hca",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    availability: Mapped[List[AvailabilityRow]] = relationship(
        back_populates="hca",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
