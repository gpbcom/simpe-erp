"""Every account and every assistant belongs to an agency.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-06

Notes:
    ``users.company_id`` and ``hcas.company_id`` were nullable because companies
    arrived after the rows that point at them. Nothing keeps that true any more:
    an account without an agency cannot be covered by per-company scoping, and
    an assistant without one produces events that cannot be routed to an
    agency's queue. Both columns become ``NOT NULL``.

    **The backfill picks the oldest company, and only when there is exactly
    one.** A deployment with a single agency — every one of them today — has an
    unambiguous answer. A deployment with several does not, and guessing would
    silently move somebody's records into another agency's scope, which is worse
    than refusing to migrate. That case raises, and the operator assigns the
    stragglers before running this again.

    A deployment with rows to backfill and **no** company at all raises for the
    same reason: there is nothing to attach them to, and inventing an agency
    here would create one nobody asked for and nobody administers.
"""

from __future__ import annotations

# Standard library imports
from typing import Sequence, Union

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES: tuple[str, ...] = ("users", "hcas")


def _resolve_company() -> str:
    """Return the company every orphaned row should be attached to.

    Returns:
        str: The identifier of the only company in the database.

    Raises:
        RuntimeError: If there is no company, or more than one, while rows
            still need one.
    """
    connection = op.get_bind()
    orphans = 0
    for table in TABLES:
        orphans += connection.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE company_id IS NULL")  # noqa: S608
        ).scalar_one()
    if orphans == 0:
        return ""
    companies = (
        connection.execute(sa.text("SELECT id FROM companies ORDER BY created_at ASC"))
        .scalars()
        .all()
    )
    if not companies:
        raise RuntimeError(
            f"{orphans} row(s) across {', '.join(TABLES)} have no company, and "
            f"there is no company to attach them to. Create the agency these "
            f"records belong to, then run this migration again."
        )
    if len(companies) > 1:
        raise RuntimeError(
            f"{orphans} row(s) across {', '.join(TABLES)} have no company, and "
            f"this database holds {len(companies)} of them. Which agency each "
            f"row belongs to is not something this migration can guess without "
            f"risking moving records into another agency's scope. Set "
            f"company_id on those rows, then run this migration again."
        )
    return companies[0]


def upgrade() -> None:
    """Backfill the orphans, then close the columns."""
    company_id = _resolve_company()
    if company_id:
        connection = op.get_bind()
        for table in TABLES:
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET company_id = :company_id "  # noqa: S608
                    f"WHERE company_id IS NULL"
                ),
                {"company_id": company_id},
            )
    for table in TABLES:
        # Batch mode, because the migration test runs against SQLite and SQLite
        # has no ALTER COLUMN. On PostgreSQL this emits the plain ALTER; on
        # SQLite Alembic rebuilds the table around the new constraint. Writing
        # the bare op would pass in production and fail the one test that
        # checks the migrations and the ORM still agree.
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "company_id",
                existing_type=sa.String(length=36),
                nullable=False,
            )


def downgrade() -> None:
    """Reopen the columns.

    Notes:
        The backfill is not undone. Which rows had no agency before is not
        recorded, and clearing them all would detach records that were always
        attached.
    """
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "company_id",
                existing_type=sa.String(length=36),
                nullable=True,
            )
