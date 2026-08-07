"""A quote, a planning run and a visit each name the agency they belong to.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-07

Notes:
    The planning computation reads every accepted quote in a period and then
    *deletes and rewrites* every visit in it. Neither statement named an agency,
    because none of these three tables carried one — so a run planning one
    agency's week built it out of every agency's accepted work and then wrote it
    over everybody's calendar. Two agencies solving overlapping periods is the
    normal case rather than a rare race: the broker gives each its own queue
    precisely so their runs proceed at the same time.

    **Denormalised rather than joined**, in all three cases, because every path
    that could reach the agency passes through a column that is allowed to be
    empty. ``quotes.authored_by`` and ``planning_runs.requested_by`` carry no
    foreign key on purpose — somebody leaving the agency must not take the
    record of what they wrote and ran with them — so neither can be the route by
    which the planner decides whose work a row is.

    **The backfill follows those same nullable paths while they still hold**,
    which is what makes it accurate for every row written by a user who is still
    on the books:

        quotes         ← the author's account
        planning_runs  ← the requester's account
        interventions  ← the run that produced them

    For anything left over — a quote whose author has gone, a run requested by a
    deleted administrator — it falls back to the policy migration 0008 set: use
    the only company when there is exactly one, and **refuse to guess** when
    there is not. A deployment with several agencies and an orphaned row gets a
    ``RuntimeError`` naming the problem rather than a row silently filed under
    somebody else's agency, which is the outcome this whole migration exists to
    prevent.
"""

from __future__ import annotations

# Standard library imports
from typing import Optional, Sequence, Union

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision: str = "0016"
down_revision: Optional[str] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES: tuple[str, ...] = ("quotes", "planning_runs", "interventions")

# Each orphan is resolved through the row that already knows the agency. The
# order matters: interventions read planning_runs, so the runs are filled first.
BACKFILLS: tuple[tuple[str, str], ...] = (
    (
        "quotes",
        "UPDATE quotes SET company_id = ("
        "  SELECT u.company_id FROM users u WHERE u.id = quotes.authored_by"
        ") WHERE company_id IS NULL AND authored_by IS NOT NULL",
    ),
    (
        "planning_runs",
        "UPDATE planning_runs SET company_id = ("
        "  SELECT u.company_id FROM users u WHERE u.id = planning_runs.requested_by"
        ") WHERE company_id IS NULL",
    ),
    (
        "interventions",
        "UPDATE interventions SET company_id = ("
        "  SELECT r.company_id FROM planning_runs r"
        "  WHERE r.id = interventions.planning_run_id"
        ") WHERE company_id IS NULL",
    ),
)


def _count_orphans() -> int:
    """Return how many rows still have no agency.

    Returns:
        int: The total across every table this migration touches.
    """
    connection = op.get_bind()
    return sum(
        connection.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE company_id IS NULL")  # noqa: S608
        ).scalar_one()
        for table in TABLES
    )


def _resolve_company() -> str:
    """Return the agency every remaining orphan should be attached to.

    Returns:
        str: The identifier of the only company in the database, or ``""`` when
        nothing is left to attach.

    Raises:
        RuntimeError: If rows still need an agency and the database holds no
            company, or more than one.

    Notes:
        The same policy as migration 0008, deliberately: a single-agency
        deployment has an unambiguous answer, and a multi-agency one does not.
        Guessing would file a quote under an agency that never wrote it, and the
        next planning run would schedule its visits and send that agency's
        assistants out to deliver them.
    """
    orphans = _count_orphans()
    if orphans == 0:
        return ""
    connection = op.get_bind()
    companies = (
        connection.execute(sa.text("SELECT id FROM companies ORDER BY created_at ASC"))
        .scalars()
        .all()
    )
    if not companies:
        raise RuntimeError(
            f"{orphans} row(s) across {', '.join(TABLES)} have no agency, and "
            f"there is no company to attach them to. Create the agency these "
            f"records belong to, then run this migration again."
        )
    if len(companies) > 1:
        raise RuntimeError(
            f"{orphans} row(s) across {', '.join(TABLES)} have no agency after "
            f"following their author, requester and planning run, and this "
            f"database holds {len(companies)} agencies. Which one each row "
            f"belongs to is not something this migration can guess without "
            f"risking scheduling one agency's work with another's assistants. "
            f"Set company_id on those rows, then run this migration again."
        )
    return companies[0]


def upgrade() -> None:
    """Add the column to all three tables, fill it, then close it."""
    for table in TABLES:
        op.add_column(
            table, sa.Column("company_id", sa.String(length=36), nullable=True)
        )

    connection = op.get_bind()
    for _, statement in BACKFILLS:
        connection.execute(sa.text(statement))

    company_id = _resolve_company()
    if company_id:
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
        # SQLite Alembic rebuilds the table around the new constraint.
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "company_id",
                existing_type=sa.String(length=36),
                nullable=False,
            )

    # Every one of these serves a query that now carries the agency: the
    # planner's own two, and the run list a manager reads.
    op.create_index("ix_quotes_company_status", "quotes", ["company_id", "status"])
    op.create_index(
        "ix_planning_runs_company", "planning_runs", ["company_id", "status"]
    )
    op.create_index(
        "ix_interventions_company_day", "interventions", ["company_id", "day"]
    )


def downgrade() -> None:
    """Drop the indexes and the columns.

    Notes:
        This restores the unscoped behaviour, which is the bug. It exists so the
        chain is reversible, not because reverting is a sensible thing to do to
        a running deployment.
    """
    op.drop_index("ix_interventions_company_day", table_name="interventions")
    op.drop_index("ix_planning_runs_company", table_name="planning_runs")
    op.drop_index("ix_quotes_company_status", table_name="quotes")
    for table in TABLES:
        op.drop_column(table, "company_id")
