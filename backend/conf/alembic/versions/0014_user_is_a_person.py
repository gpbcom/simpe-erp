"""Split the account's display name in two, now that a User is a Person.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-07

Notes:
    ``users.full_name`` becomes ``users.first_name`` + ``users.last_name``, so
    an account carries the same name fields as every other person the system
    holds — which is what lets :class:`~models.auth.user.User` extend
    :class:`~models.base.person.Person` instead of restating its validators.

    **The split is on the first space, and it round-trips exactly.**
    ``"Jean Pierre de la Tour"`` stores ``"Jean"`` and ``"Pierre de la Tour"``,
    and :meth:`~models.auth.user.User.full_name` rejoins them into the string
    that was there before. Splitting on the *last* space would not: it would
    turn the same name into ``"Jean Pierre de la"`` and ``"Tour"``, which reads
    back identically but files the person under the wrong surname.

    **A name with no space goes entirely into ``last_name``**, leaving
    ``first_name`` empty. A mononym and a service account called ``root`` are
    both real, and inventing a given name for them would be worse than leaving
    the column blank. The model permits an empty given name on an account for
    exactly this reason, and on no other person type.

    Both columns are ``NOT NULL`` with a server-side default of ``''`` so the
    backfill can run against existing rows before the constraint bites. The
    default is dropped afterwards: a default left in place is one somebody
    eventually relies on without noticing which value it is.

    The downgrade recombines the two with a single space, which is lossless for
    every row this migration wrote.
"""

from __future__ import annotations

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the two name columns, backfill them, and drop the display name."""
    op.add_column(
        "users",
        sa.Column(
            "first_name", sa.String(length=255), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "last_name", sa.String(length=255), nullable=False, server_default=""
        ),
    )

    # Split in Python, not in SQL. The obvious SQL spelling needs a
    # substring-position function, and the two databases this runs on disagree
    # about its name — ``instr`` on SQLite, ``strpos`` on PostgreSQL — so a
    # single expression would pass the test suite and fail the deployment.
    # The cost is a full read of ``users``, which is an agency's staff list:
    # hundreds of rows, not the table anything hot is keyed on.
    users = sa.table(
        "users",
        sa.column("id", sa.String),
        sa.column("full_name", sa.String),
        sa.column("first_name", sa.String),
        sa.column("last_name", sa.String),
    )
    connection = op.get_bind()
    for identifier, display_name in connection.execute(
        sa.select(users.c.id, users.c.full_name)
    ).all():
        given, _, family = (display_name or "").strip().partition(" ")
        connection.execute(
            users.update()
            .where(users.c.id == identifier)
            .values(
                first_name=given if family else "",
                last_name=(family.strip() or given),
            )
        )

    with op.batch_alter_table("users") as batch:
        batch.alter_column("first_name", server_default=None)
        batch.alter_column("last_name", server_default=None)
        batch.drop_column("full_name")


def downgrade() -> None:
    """Restore the single display name from the two halves."""
    op.add_column(
        "users",
        sa.Column(
            "full_name", sa.String(length=255), nullable=False, server_default=""
        ),
    )
    users = sa.table(
        "users",
        sa.column("full_name", sa.String),
        sa.column("first_name", sa.String),
        sa.column("last_name", sa.String),
    )
    op.execute(
        users.update().values(
            full_name=sa.func.trim(
                users.c.first_name + sa.literal(" ") + users.c.last_name
            )
        )
    )
    with op.batch_alter_table("users") as batch:
        batch.alter_column("full_name", server_default=None)
        batch.drop_column("last_name")
        batch.drop_column("first_name")
