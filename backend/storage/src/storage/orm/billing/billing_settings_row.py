from __future__ import annotations

# Standard library imports
from datetime import datetime
from decimal import Decimal
from typing import Optional

# Third-party imports
from sqlalchemy import Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

# First-party imports
from storage.orm.base import Base


class BillingSettingsRow(Base):
    """The ``billing_settings`` table.

    Attributes:
        id (str): Primary key; always the singleton identifier.
        periodicity (str): How often customers are invoiced.
        payment_terms_days (int): How long a customer has to pay.
        late_penalty_multiplier (int): Times the legal interest rate a late
            payment is charged at.
        recovery_indemnity_eur (Decimal): The fixed recovery indemnity.
        escompte_offered (bool): Whether a discount for early settlement is
            offered.
        updated_by (Optional[str]): The account that last changed these.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last-update timestamp.

    Notes:
        - One row, with a fixed textual primary key rather than a UUID, exactly
          as the planning rules have. These are agency-wide; a table that can
          hold two of them raises the question of which one an invoice was
          issued under, and a printed document cannot answer that afterwards.
        - ``updated_by`` is deliberately not a foreign key to ``users``. It is
          an audit trail, and one that disappears when the account is deleted is
          not one — "who put the payment terms to sixty days?" outlives the
          person who left.
        - Every column here is printed on an invoice. That is the test for
          whether a setting belongs in this table rather than in ``app.yaml``.
    """

    __tablename__ = "billing_settings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    periodicity: Mapped[str] = mapped_column(String(16), nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=False)
    late_penalty_multiplier: Mapped[int] = mapped_column(Integer, nullable=False)
    recovery_indemnity_eur: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    escompte_offered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(Base.ID_LENGTH), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
