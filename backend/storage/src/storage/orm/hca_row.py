from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

# Third-party imports
from sqlalchemy import DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

# First-party imports
from storage.orm.base import Base

if TYPE_CHECKING:
    # First-party imports
    from storage.orm.availability_row import AvailabilityRow
    from storage.orm.certification_row import CertificationRow


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
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.
        certifications (List[CertificationRow]): Qualifications held.
        availability (List[AvailabilityRow]): Recorded absences.

    Notes:
        - The licence is flattened into four nullable columns rather than given
          its own table. It is strictly one-per-assistant, so a table would add a
          join for no gain; ``driving_license_categories`` being ``NULL`` is what
          distinguishes "no licence" from "a licence with no category recorded".
        - Certifications and availability *are* separate tables: both are
          one-to-many, and availability is queried by date range on every solve.
        - Both children cascade on delete. An orphaned absence would silently
          block scheduling for an assistant who no longer exists.
    """

    __tablename__ = "hcas"
    __table_args__ = (
        Index("ix_hcas_last_name", "last_name"),
        Index("ix_hcas_contract_type", "contract_type"),
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
    geocoding_error: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    company_id: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
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
    availability: Mapped[List[AvailabilityRow]] = relationship(
        back_populates="hca",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
