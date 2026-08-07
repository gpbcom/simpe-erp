from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Optional

# Third-party imports
from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class CustomerRow(Base):
    """The ``customers`` table.

    Attributes:
        id (str): UUID primary key.
        first_name (str): Given name.
        last_name (str): Family name.
        phone_number (str): Contact telephone number, canonical form.
        email (str): Contact email address.
        street (str): Street line of the delivery address.
        postal_code (str): Postal code of the delivery address.
        city (str): City of the delivery address.
        country (str): Country of the delivery address.
        latitude (Optional[float]): Resolved latitude, when geocoded.
        longitude (Optional[float]): Resolved longitude, when geocoded.
        geocoding_error (Optional[str]): Stable code for a geocoding failure.
        registration_status (str): ``active`` or ``stopped``.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.

    Notes:
        - The address is flattened into columns rather than stored as a JSON
          blob. The planner filters and reads coordinates on every solve, and a
          blob would make ``latitude``/``longitude`` unindexable and every read
          a deserialisation.
        - The email is **not** unique: customers are not accounts, and two people
          at one address legitimately share a contact address.
    """

    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_last_name", "last_name"),
        Index("ix_customers_registration_status", "registration_status"),
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
    registration_status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
