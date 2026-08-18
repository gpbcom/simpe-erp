"""Hold an agency's contract with a certified e-invoicing platform.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-11

Notes:
    The reform routes every invoice through an intermediary the tax authority
    recognises, and the public exchange service that would have been free was
    withdrawn. So an agency must contract with a platform, and this table is
    where that contract becomes state: which platform, whether it is switched
    on, and the credentials to reach it.

    **The credentials are stored encrypted and the column is ``TEXT``.** Fernet
    output grows with its payload, and the payload grows the day a platform
    wants a reference this application does not carry yet. A column sized to
    today's four fields would fail on a save, in production, months from now.

    **Two constraints, saying different things.** The unique constraint over
    ``(company_id, provider)`` stops an agency holding two keys for one platform
    with no way to say which one an invoice went out under. The *partial* unique
    index over ``company_id`` stops it enabling two platforms at once — partial,
    because an agency may hold any number of *disabled* platforms and a plain
    unique constraint could not express the difference.

    Nothing is backfilled, and nothing needs to be: no agency has connected a
    platform, so an empty table is the correct history. What that means for
    every existing agency is that they have no active integration — which is
    what the warning banner on the billing screens exists to say out loud.
"""

from __future__ import annotations

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

#: The table this revision introduces.
TABLE = "einvoicing_integrations"

#: One key per agency per platform.
UNIQUE_PROVIDER = "uq_einvoicing_company_provider"

#: One *enabled* platform per agency. Disabled rows are unconstrained.
UNIQUE_ENABLED = "uq_einvoicing_one_enabled_per_company"


def upgrade() -> None:
    """Create the integrations table and its two constraints."""
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("credential_ciphertext", sa.Text(), nullable=False),
        sa.Column(
            "credential_hint", sa.String(length=16), nullable=False, server_default=""
        ),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_error", sa.String(length=512), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "provider", name=UNIQUE_PROVIDER),
    )
    op.create_index(f"ix_{TABLE}_company_id", TABLE, ["company_id"], unique=False)
    # The one-active rule, enforced where the application cannot lose it. A
    # second write path to this table — a fixture, a support script, a future
    # endpoint — inherits the invariant rather than having to remember it.
    op.create_index(
        UNIQUE_ENABLED,
        TABLE,
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("enabled"),
        sqlite_where=sa.text("enabled"),
    )


def downgrade() -> None:
    """Drop the integrations table.

    Notes:
        Dropping it discards every stored credential. That is recoverable only
        by re-entering each platform's API key, which is the same cost as losing
        the encryption key — and the reason both are worth saying out loud in
        the deployment notes rather than only here.
    """
    op.drop_index(UNIQUE_ENABLED, table_name=TABLE)
    op.drop_index(f"ix_{TABLE}_company_id", table_name=TABLE)
    op.drop_table(TABLE)
