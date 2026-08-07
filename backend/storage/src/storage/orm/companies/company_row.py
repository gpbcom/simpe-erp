from __future__ import annotations

# Standard library imports
from datetime import datetime
from decimal import Decimal
from typing import Optional

# Third-party imports
from sqlalchemy import Boolean, DateTime, Float, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class CompanyRow(Base):
    """The ``companies`` table.

    Attributes:
        id (str): UUID primary key.
        name (str): Trading name; unique.
        registration_number (Optional[str]): Company registration number.
        contact_email (Optional[str]): Where an applicant's questions go.
        legal_form (Optional[str]): SARL, SAS, Association and so on.
        share_capital (Optional[Decimal]): Share capital, in euros.
        rcs_number (Optional[str]): Trade-register entry.
        vat_number (Optional[str]): Intra-community VAT number.
        phone_number (Optional[str]): Contact telephone number.
        street (Optional[str]): Registered office street.
        postal_code (Optional[str]): Registered office postal code.
        city (Optional[str]): Registered office city.
        country (Optional[str]): Registered office country.
        latitude (Optional[float]): Resolved latitude of the office.
        longitude (Optional[float]): Resolved longitude of the office.
        geocoding_error (Optional[str]): Why the office did not resolve.
        is_accepting_applications (bool): Whether it appears publicly.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.

    Notes:
        The name is unique. An applicant choosing between two identically named
        agencies is choosing at random, and the one they meant is the one they
        will not be able to identify afterwards.

        The address is flattened into columns rather than stored as JSON,
        matching every other address in this schema, so a query can filter on a
        city without unpacking a document.
    """

    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_name", "name", unique=True),
        Index("ix_companies_accepting", "is_accepting_applications"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    registration_number: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    contact_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    legal_form: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    share_capital: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    rcs_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    vat_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    street: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    geocoding_error: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_accepting_applications: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
