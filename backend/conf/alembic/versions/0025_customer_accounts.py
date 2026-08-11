"""Let a customer sign in to their own space.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-11

Notes:
    Until now an account could only be staff. ``users.role`` held one of three
    values and ``users.hca_id`` was the only link to a person, so a customer had
    no way in at all — every screen in the product was built for the agency.

    **No widening of ``role`` is needed, and that is checked rather than
    assumed.** The column is ``String(16)``; ``"customer"`` is eight characters.
    Migration 0006 exists because exactly this was missed once — ``status`` was
    sized when ``accepted`` was the longest value, ``pending-validation`` is
    eighteen, and SQLite truncates in silence while PostgreSQL errors. The
    arithmetic is done here so nobody has to repeat it.

    **``customer_id`` is nullable and nothing is backfilled.** Every existing
    account is staff, and staff must *not* carry the link — the model refuses to
    build an account that has both a staff role and a customer link, because
    such an account passes the staff guards and resolves to one household at the
    same time. Null is therefore the correct value for every row that exists
    today, and for every staff row ever created.

    The foreign key is ``ON DELETE RESTRICT``, matching ``hca_id``. The database
    must never be left holding an account that points at a household that no
    longer exists; ``CustomerService.delete`` removes the portal account in the
    same transaction, so the constraint is a backstop for a path added later,
    not part of the ordinary flow.
"""

from __future__ import annotations

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Link an account to the household it belongs to."""
    op.add_column(
        "users",
        sa.Column("customer_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_users_customer_id", "users", ["customer_id"])
    # Named explicitly. An unnamed constraint is one SQLite cannot drop in the
    # downgrade, and the batch operation below needs to address it.
    with op.batch_alter_table("users") as batch:
        batch.create_foreign_key(
            "fk_users_customer_id",
            "customers",
            ["customer_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    """Remove the customer link.

    Notes:
        Any portal account goes with the column. There is no way to keep one —
        an account whose role is ``customer`` and whose link has been dropped is
        exactly the state the model refuses to build.
    """
    op.execute(sa.text("DELETE FROM users WHERE role = 'customer'"))
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("fk_users_customer_id", type_="foreignkey")
    op.drop_index("ix_users_customer_id", table_name="users")
    op.drop_column("users", "customer_id")
