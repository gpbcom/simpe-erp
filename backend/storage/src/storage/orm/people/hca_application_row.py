from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Optional

# Third-party imports
from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class HcaApplicationRow(Base):
    """The ``hca_applications`` table.

    Attributes:
        id (str): UUID primary key.
        company_id (str): The company applied to.
        first_name (str): Given name.
        last_name (str): Family name.
        phone_number (str): Contact telephone number.
        email (str): The address that becomes the sign-in on approval.
        street (str): Home street.
        postal_code (str): Home postal code.
        city (str): Home city.
        country (str): Home country.
        latitude (Optional[float]): Resolved latitude of the home.
        longitude (Optional[float]): Resolved longitude of the home.
        geocoding_error (Optional[str]): Why the home did not resolve.
        contract_type (Optional[str]): The contract applied for.
        hashed_password (str): The chosen credential, hashed.
        status (str): ``pending``, ``approved`` or ``rejected``.
        decided_by (Optional[str]): The manager who decided it.
        decided_at (Optional[datetime]): When it was decided.
        rejection_reason (Optional[str]): Why it was declined.
        hca_id (Optional[str]): The assistant record created on approval.
        created_at (datetime): When it was submitted.
        updated_at (datetime): Last-update timestamp.

    Notes:
        - ``email`` is **not** unique here, unlike on ``users``. Somebody
          declined by one agency may apply to another, and somebody whose
          application lapsed may apply again; a unique index would refuse both.
          Uniqueness is enforced where it belongs, on the account created at
          approval.
        - ``company_id`` restricts on delete rather than cascading. A company
          with applications against it has a decision history, and removing the
          row would silently take that with it.
        - ``hashed_password`` holds a hash, never a password. An application can
          wait days for a decision, and a plaintext credential waiting days is a
          plaintext credential in every backup taken meanwhile.
    """

    __tablename__ = "hca_applications"
    __table_args__ = (
        Index("ix_hca_applications_company", "company_id"),
        Index("ix_hca_applications_status", "status"),
        Index("ix_hca_applications_email", "email"),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
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
    contract_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    decided_by: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hca_id: Mapped[Optional[str]] = mapped_column(String(Base.ID_LENGTH), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
