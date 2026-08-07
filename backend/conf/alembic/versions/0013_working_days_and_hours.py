"""Make the working day configurable and record each assistant's week.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-07

Notes:
    Two changes arrive together because they answer the same question from the
    two ends. "When is work allowed?" was previously answered only by
    ``app.yaml`` — the same for everybody, and changeable only by a
    deployment. After this it is answered by the agency's stored settings for
    the *hours*, and by each assistant's own record for the *days*.

    - ``planning_settings`` gains ``day_start_minute``, ``day_end_minute``,
      ``lunch_window_start_minute`` and ``lunch_window_end_minute``. They join
      ``lunch_break_minutes``, which was already there, so the six values the
      solver bounds a day with now live in one row a manager owns.
    - ``hcas.working_weekdays`` holds the days of the week that assistant works
      at all, comma-separated and ordered Monday first.

    **The two backfills are the load-bearing part of this migration, and they
    disagree on purpose.**

    The four ``planning_settings`` columns are backfilled with the same
    defaults the configuration file shipped — 09:00 to 20:00, lunch between
    11:30 and 14:30. The single stored row was written under those values, so
    this is not a new policy, it is the existing one written down where it can
    now be changed.

    ``working_weekdays`` is backfilled with **all seven days**, not with
    Monday-to-Friday, even though Monday-to-Friday is what a newly created
    assistant gets. This is the same reasoning migration 0012 applied to
    ``field_employee``: every assistant that existed before this column did was
    somebody the planner could schedule on any day it had work for them, and
    narrowing them to a five-day week here would cancel Saturday and Sunday
    rounds that nobody asked to cancel — silently, and only visibly as a
    planning run that suddenly cannot place a weekend visit. The default for
    *new* records belongs to the application's model; what belongs here is
    leaving the existing ones as they were.

    The server defaults are dropped immediately after the backfill, for the
    reason 0012 gives: the value belongs to the application's model, and a
    database-side default is a second place for it to be decided.
"""

from __future__ import annotations

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

# The working day the configuration file has always shipped, in minutes from
# midnight. Spelled out rather than imported from PlanningConfig: a migration
# has to keep meaning the same thing after somebody edits that class, and an
# import would make this revision's behaviour depend on the code it runs
# against rather than on the schema it was written for.
DEFAULT_DAY_START_MINUTE = 9 * 60
DEFAULT_DAY_END_MINUTE = 20 * 60
DEFAULT_LUNCH_WINDOW_START_MINUTE = 11 * 60 + 30
DEFAULT_LUNCH_WINDOW_END_MINUTE = 14 * 60 + 30

# Every day of the week, in the order the mapper writes them.
ALL_WEEKDAYS = "monday,tuesday,wednesday,thursday,friday,saturday,sunday"

SETTINGS_COLUMNS = (
    ("day_start_minute", DEFAULT_DAY_START_MINUTE),
    ("day_end_minute", DEFAULT_DAY_END_MINUTE),
    ("lunch_window_start_minute", DEFAULT_LUNCH_WINDOW_START_MINUTE),
    ("lunch_window_end_minute", DEFAULT_LUNCH_WINDOW_END_MINUTE),
)


def upgrade() -> None:
    """Add the working-day columns and the per-assistant working week."""
    for column_name, default_minute in SETTINGS_COLUMNS:
        op.add_column(
            "planning_settings",
            sa.Column(
                column_name,
                sa.Integer(),
                nullable=False,
                server_default=sa.text(str(default_minute)),
            ),
        )
    with op.batch_alter_table("planning_settings") as batch:
        for column_name, _ in SETTINGS_COLUMNS:
            batch.alter_column(
                column_name,
                existing_type=sa.Integer(),
                server_default=None,
            )

    op.add_column(
        "hcas",
        sa.Column(
            "working_weekdays",
            sa.String(length=80),
            nullable=False,
            server_default=sa.text(f"'{ALL_WEEKDAYS}'"),
        ),
    )
    with op.batch_alter_table("hcas") as batch:
        batch.alter_column(
            "working_weekdays",
            existing_type=sa.String(length=80),
            server_default=None,
        )


def downgrade() -> None:
    """Drop the working-day columns and the per-assistant working week.

    Notes:
        **This loses the working weeks and there is nowhere to put them.** No
        earlier column holds "this assistant never works Wednesdays", so every
        such declaration is discarded. The hours are recoverable — they revert
        to whatever ``app.yaml`` carries, which is where they came from — but
        an agency that had moved its day to 08:00–19:00 through the API silently
        goes back to the deployed values.
    """
    op.drop_column("hcas", "working_weekdays")
    for column_name, _ in SETTINGS_COLUMNS:
        op.drop_column("planning_settings", column_name)
