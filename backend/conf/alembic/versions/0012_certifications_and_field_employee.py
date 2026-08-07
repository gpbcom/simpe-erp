"""Add the certification catalogue, its requirements, and the rounds flag.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-07

Notes:
    Four changes arrive together because they are one feature: a qualification
    is only worth cataloguing if something can require it, and a requirement is
    only enforceable if the planner knows who may be scheduled at all.

    - ``certification_types`` is the catalogue. Its ``code`` is what everything
      else refers to, and it is unique.
    - ``certifications.code`` links a person's stored qualification to a
      catalogue entry. **Nullable, and with no foreign key.** The catalogue
      arrived after the records did, so a qualification typed before it existed
      has no code and is still somebody's qualification — making the link
      mandatory would have meant inventing a catalogue entry for every distinct
      spelling already stored, and getting some of them wrong.
    - ``intervention_types.required_certification_codes`` and
      ``quote_lines.required_certification_codes`` hold the requirement, as
      JSON arrays. A foreign key cannot reach inside one, so both are validated
      in the service on the way in, where an unknown code can be reported by
      name instead of as an integrity error.
    - ``hcas.field_employee`` decides who the planner may schedule.

    **The two defaults are the load-bearing part of this migration.**

    ``field_employee`` is added with a server default of true which is then
    dropped. Every assistant that existed before this column did was, by
    definition, somebody the planner was already free to schedule; a default of
    false would have emptied the workforce on the deployment that introduced it
    and failed every planning run until somebody ticked a box they had not been
    told about. Dropping the default afterwards is deliberate too: the value
    belongs to the application's own model, and a database-side default is a
    second place for it to be decided.

    ``required_certification_codes`` on ``intervention_types`` is backfilled to
    an empty array, so no service already being sold suddenly requires
    something nobody holds. The quote-line column stays nullable, because
    ``NULL`` there means "inherit the catalog entry" and is not the same
    statement as an empty array — which means "this hour needs no qualification
    at all".
"""

from __future__ import annotations

# Third-party imports
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# The same variant the ORM base declares: ``JSONB`` against PostgreSQL, plain
# ``JSON`` on SQLite. The migration test suite runs against SQLite and
# production runs against PostgreSQL, so a migration that only works on one of
# them is one nobody can test.
JSON_TYPE = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    """Create the catalogue and add the four columns that use it."""
    op.create_table(
        "certification_types",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_certification_types_code_unique",
        "certification_types",
        ["code"],
        unique=True,
    )
    op.create_index(
        "ix_certification_types_is_active",
        "certification_types",
        ["is_active"],
    )

    op.add_column(
        "certifications",
        sa.Column("code", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_certifications_code", "certifications", ["code"])

    op.add_column(
        "intervention_types",
        sa.Column("required_certification_codes", JSON_TYPE, nullable=True),
    )
    op.execute(
        "UPDATE intervention_types SET required_certification_codes = '[]' "
        "WHERE required_certification_codes IS NULL"
    )
    with op.batch_alter_table("intervention_types") as batch:
        batch.alter_column(
            "required_certification_codes",
            existing_type=JSON_TYPE,
            nullable=False,
        )

    op.add_column(
        "quote_lines",
        sa.Column("required_certification_codes", JSON_TYPE, nullable=True),
    )

    op.add_column(
        "hcas",
        sa.Column(
            "field_employee",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    with op.batch_alter_table("hcas") as batch:
        batch.alter_column(
            "field_employee",
            existing_type=sa.Boolean(),
            server_default=None,
        )
    op.create_index("ix_hcas_field_employee", "hcas", ["field_employee"])


def downgrade() -> None:
    """Drop the columns and the catalogue.

    Notes:
        **This loses data, and there is nowhere to put it.** Every recorded
        requirement, every link from a person's qualification to a catalogue
        entry, and every decision about who goes out on rounds is discarded —
        none of them existed before this revision, so no earlier column can
        hold them. Downgrading and upgrading again leaves every service
        requiring nothing and every assistant back on the rounds, which is the
        state this revision started from and the safest of the possible
        reconstructions: it schedules people who should not be scheduled rather
        than silently leaving customers unvisited, and it is visible on screen.
    """
    op.drop_index("ix_hcas_field_employee", table_name="hcas")
    with op.batch_alter_table("hcas") as batch:
        batch.drop_column("field_employee")

    with op.batch_alter_table("quote_lines") as batch:
        batch.drop_column("required_certification_codes")

    with op.batch_alter_table("intervention_types") as batch:
        batch.drop_column("required_certification_codes")

    op.drop_index("ix_certifications_code", table_name="certifications")
    with op.batch_alter_table("certifications") as batch:
        batch.drop_column("code")

    op.drop_index("ix_certification_types_is_active", table_name="certification_types")
    op.drop_index(
        "ix_certification_types_code_unique", table_name="certification_types"
    )
    op.drop_table("certification_types")
