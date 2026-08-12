from __future__ import annotations

# Standard library imports
from datetime import datetime
from decimal import Decimal
from typing import Optional

# Third-party imports
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class AgencyRow(Base):
    """The ``agencies`` table: one of a company's places.

    Attributes:
        id (str): UUID primary key.
        company_id (str): The company this site belongs to.
        name (str): What the site is called.
        agency_type (str): ``hq``, ``warehouse`` or ``office``.
        legal_form (Optional[str]): SARL, SAS, Association and so on.
        share_capital (Optional[Decimal]): Share capital, in euros.
        rcs_number (Optional[str]): Trade-register entry.
        vat_number (Optional[str]): Intra-community VAT number.
        sap_declaration_number (Optional[str]): Services-à-la-personne
            declaration number, printed on invoices.
        phone_number (Optional[str]): Contact telephone number.
        registration_number (Optional[str]): Company registration number.
        contact_email (Optional[str]): Where questions go.
        iban (Optional[str]): Account the agency is paid into.
        bic (Optional[str]): Bank identifier code of that account.
        logo_url (Optional[str]): URL of the logo in the object store.
        is_accepting_applications (bool): Whether it appears publicly.
        street (Optional[str]): Site street.
        postal_code (Optional[str]): Site postal code.
        city (Optional[str]): Site city.
        country (Optional[str]): Site country.
        latitude (Optional[float]): Resolved latitude of the site.
        longitude (Optional[float]): Resolved longitude of the site.
        geocoding_error (Optional[str]): Why the site did not resolve.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.

    Notes:
        - The address is flattened into columns rather than stored as JSON,
          matching every other address in this schema. Here it matters more than
          usual: the quote-to-team rule reads the coordinate on every quote
          written, and a document would have to be unpacked to do it.
        - ``uq_agencies_company_hq`` is a **partial** unique index, and it is
          what makes "a company has one head office" a fact of the database
          rather than a service's good intentions. It is declared with both
          ``postgresql_where`` and ``sqlite_where`` because the suite runs on
          SQLite and the deployment on PostgreSQL — an invariant that holds in
          only one of them is an invariant the tests cannot prove.
        - The foreign key to ``companies`` is ``RESTRICT`` rather than
          ``CASCADE``. Deleting a company out from under its sites would take
          the teams, the plannings and the quotes with them in one statement
          nobody confirmed; the refusal is the point.
        - **The company's own columns are repeated here**, because a site *is*
          a company in the model: the head office is where the business is
          registered, and a quote prints its SIRET, its VAT number and its bank
          details from the site it was written at. Every one is nullable, as on
          ``companies`` — and the model refuses to let a branch fill them in, so
          the repetition cannot become two answers to "which company is this".
    """

    __tablename__ = "agencies"
    __table_args__ = (
        Index("ix_agencies_company", "company_id"),
        Index("uq_agencies_company_name", "company_id", "name", unique=True),
        Index(
            "uq_agencies_company_hq",
            "company_id",
            unique=True,
            postgresql_where=text("agency_type = 'hq'"),
            sqlite_where=text("agency_type = 'hq'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(Base.ID_LENGTH), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(Base.ID_LENGTH),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    agency_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # The company's own columns, because a site *is* a company in the model —
    # the head office is where the business is registered. Every one is
    # nullable, exactly as on ``companies``: an agency that has not filled in
    # its RCS entry prints without it.
    legal_form: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    share_capital: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    rcs_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    vat_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sap_declaration_number: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    phone_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    registration_number: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    contact_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    iban: Mapped[Optional[str]] = mapped_column(String(34), nullable=True)
    bic: Mapped[Optional[str]] = mapped_column(String(11), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_accepting_applications: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    street: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # noqa: E501
    city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    geocoding_error: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # noqa: E501
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
