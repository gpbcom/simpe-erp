"""People and accounts: customers, assistants, certifications, availability, users.

Revision ID: 0001
Revises:
Create Date: 2026-08-05

Notes:
    ``hcas`` is created before ``users`` because the account table carries a
    foreign key to it.
"""

from __future__ import annotations

# Standard library imports
from typing import Sequence, Union

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the people and account tables."""
    op.create_table(
        "customers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("first_name", sa.String(128), nullable=False),
        sa.Column("last_name", sa.String(128), nullable=False),
        sa.Column("phone_number", sa.String(32), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("street", sa.String(255), nullable=False),
        sa.Column("postal_code", sa.String(16), nullable=False),
        sa.Column("city", sa.String(128), nullable=False),
        sa.Column("country", sa.String(128), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("geocoding_error", sa.String(32), nullable=True),
        sa.Column("registration_status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_customers_last_name", "customers", ["last_name"])
    op.create_index(
        "ix_customers_registration_status", "customers", ["registration_status"]
    )

    op.create_table(
        "hcas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("first_name", sa.String(128), nullable=False),
        sa.Column("last_name", sa.String(128), nullable=False),
        sa.Column("phone_number", sa.String(32), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("street", sa.String(255), nullable=False),
        sa.Column("postal_code", sa.String(16), nullable=False),
        sa.Column("city", sa.String(128), nullable=False),
        sa.Column("country", sa.String(128), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("geocoding_error", sa.String(32), nullable=True),
        sa.Column("contract_type", sa.String(16), nullable=False),
        sa.Column("driving_license_categories", sa.String(64), nullable=True),
        sa.Column("driving_license_number", sa.String(64), nullable=True),
        sa.Column(
            "driving_license_obtained_on", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "driving_license_expires_on", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_hcas_last_name", "hcas", ["last_name"])
    op.create_index("ix_hcas_contract_type", "hcas", ["contract_type"])

    op.create_table(
        "certifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "hca_id",
            sa.String(36),
            sa.ForeignKey("hcas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("issuer", sa.String(255), nullable=True),
        sa.Column("obtained_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
    )
    op.create_index("ix_certifications_hca_id", "certifications", ["hca_id"])

    op.create_table(
        "availability_slots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "hca_id",
            sa.String(36),
            sa.ForeignKey("hcas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_availability_hca_period",
        "availability_slots",
        ["hca_id", "start_date", "end_date"],
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "hca_id",
            sa.String(36),
            sa.ForeignKey("hcas.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email_unique", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_hca_id", "users", ["hca_id"])


def downgrade() -> None:
    """Drop the people and account tables.

    Notes:
        Dropped in reverse dependency order so no foreign key is left pointing
        at a table that no longer exists.
    """
    op.drop_table("users")
    op.drop_table("availability_slots")
    op.drop_table("certifications")
    op.drop_table("hcas")
    op.drop_table("customers")
