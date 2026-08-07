"""Companies, assistants' applications, and the manager-owned planning rules.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-05

Notes:
    Three things land together because they arrived together: an assistant can
    now register themselves (which needs a company to apply to and a queue to
    wait in), an administrator can create an account with a temporary password
    (which needs the three account columns), and the intervention radius is now
    a manager's decision rather than a deployment's.

    ``users.must_change_password`` and ``users.account_origin`` are created
    ``NOT NULL`` with server-side defaults so that the accounts already in the
    table get a correct value rather than a null: everything existing was
    self-registered and has already chosen its own password, which is exactly
    what those defaults say.
"""

from __future__ import annotations

# Standard library imports
from typing import Optional, Sequence, Union

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Optional[str] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the new tables and columns."""
    op.create_table(
        "companies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("registration_number", sa.String(64), nullable=True),
        sa.Column("contact_email", sa.String(320), nullable=True),
        sa.Column("street", sa.String(255), nullable=True),
        sa.Column("postal_code", sa.String(16), nullable=True),
        sa.Column("city", sa.String(128), nullable=True),
        sa.Column("country", sa.String(128), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("geocoding_error", sa.String(32), nullable=True),
        sa.Column("is_accepting_applications", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_companies_name", "companies", ["name"], unique=True)
    op.create_index(
        "ix_companies_accepting", "companies", ["is_accepting_applications"]
    )

    op.create_table(
        "hca_applications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
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
        sa.Column("contract_type", sa.String(16), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decided_by", sa.String(36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("hca_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_hca_applications_company", "hca_applications", ["company_id"])
    op.create_index("ix_hca_applications_status", "hca_applications", ["status"])
    op.create_index("ix_hca_applications_email", "hca_applications", ["email"])

    op.create_table(
        "planning_settings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("max_intervention_radius_km", sa.Float(), nullable=False),
        sa.Column("lunch_break_minutes", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.add_column("hcas", sa.Column("company_id", sa.String(36), nullable=True))
    op.add_column("users", sa.Column("company_id", sa.String(36), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "account_origin",
            sa.String(24),
            nullable=False,
            server_default="self-registered",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Drop the new tables and columns, children first."""
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "account_origin")
    op.drop_column("users", "company_id")
    op.drop_column("hcas", "company_id")
    op.drop_table("planning_settings")
    op.drop_table("hca_applications")
    op.drop_table("companies")
