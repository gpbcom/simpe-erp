"""Add the skill catalogue, self-declared skills, and their requirements.

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-07

Notes:
    Four changes arrive together because they are one feature: a skill is only
    worth cataloguing if something can require it, and a requirement is only
    enforceable if somebody can declare that they meet it.

    - ``skill_types`` is the catalogue. Its ``code`` is what everything else
      refers to, and it is unique.
    - ``skills`` is what an assistant declares about themselves. It is a new
      table rather than rows in ``certifications`` with a discriminator: the
      two are written by different people through different routes, and the
      employment form replaces the certification list *wholesale*, so sharing
      a table would have made a manager saving a contract change silently
      delete every skill the assistant had declared.
    - ``intervention_types.required_skill_codes`` and
      ``quote_lines.required_skill_codes`` hold the requirement, as JSON
      arrays, mirroring the certification columns migration 0012 added. A
      foreign key cannot reach inside one, so both are validated in the service
      on the way in, where an unknown code can be reported by name instead of
      as an integrity error.

    **The backfill is the load-bearing part of this migration**, and it is a
    backfill to *nothing*.

    ``required_skill_codes`` on ``intervention_types`` is filled with an empty
    array and only then made ``NOT NULL``, so no service already being sold
    suddenly requires a skill nobody has declared — which would fail every
    planning run touching it on the deployment that shipped this. The
    quote-line column stays nullable, because ``NULL`` there means "inherit the
    catalog entry" and is not the same statement as an empty array, which means
    "this hour needs no skill at all".

    Nothing backfills ``skills``. Every assistant starts having declared
    nothing, which is the truth: nobody has been asked yet. Combined with the
    empty requirement arrays it means this revision changes no planning
    outcome at all on the day it lands, which is the property that makes it
    safe to deploy separately from the screens that use it.
"""

from __future__ import annotations

# Third-party imports
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# The same variant the ORM base declares: ``JSONB`` against PostgreSQL, plain
# ``JSON`` on SQLite. The migration test suite runs against SQLite and
# production runs against PostgreSQL, so a migration that only works on one of
# them is one nobody can test.
JSON_TYPE = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    """Create the catalogue, the declarations table, and the two columns."""
    op.create_table(
        "skill_types",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_skill_types_code_unique",
        "skill_types",
        ["code"],
        unique=True,
    )
    op.create_index("ix_skill_types_is_active", "skill_types", ["is_active"])

    op.create_table(
        "skills",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "hca_id",
            sa.String(length=36),
            sa.ForeignKey("hcas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        # Nullable and with no foreign key, exactly like ``certifications.code``
        # and for the same two reasons: somebody may declare a skill the
        # catalogue has no name for yet, and the matching side of the pair is a
        # JSON array a constraint cannot reach into anyway.
        sa.Column("code", sa.String(length=32), nullable=True),
        sa.Column("issuer", sa.String(length=255), nullable=True),
        sa.Column("obtained_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
    )
    op.create_index("ix_skills_hca_id", "skills", ["hca_id"])
    op.create_index("ix_skills_code", "skills", ["code"])

    op.add_column(
        "intervention_types",
        sa.Column("required_skill_codes", JSON_TYPE, nullable=True),
    )
    op.execute(
        "UPDATE intervention_types SET required_skill_codes = '[]' "
        "WHERE required_skill_codes IS NULL"
    )
    with op.batch_alter_table("intervention_types") as batch:
        batch.alter_column(
            "required_skill_codes",
            existing_type=JSON_TYPE,
            nullable=False,
        )

    op.add_column(
        "quote_lines",
        sa.Column("required_skill_codes", JSON_TYPE, nullable=True),
    )


def downgrade() -> None:
    """Drop the columns, the declarations and the catalogue.

    Notes:
        **This loses data, and there is nowhere to put it.** Every skill
        anybody declared and every requirement naming one is discarded. None of
        them existed before this revision, so no earlier column can hold them.
        Downgrading and upgrading again leaves every service requiring no skill
        and every assistant having declared none, which is the state this
        revision started from and the safe direction to fail in: it widens who
        may be sent to a visit rather than leaving customers unvisited, and the
        emptied profiles are visible on screen.
    """
    with op.batch_alter_table("quote_lines") as batch:
        batch.drop_column("required_skill_codes")

    with op.batch_alter_table("intervention_types") as batch:
        batch.drop_column("required_skill_codes")

    op.drop_index("ix_skills_code", table_name="skills")
    op.drop_index("ix_skills_hca_id", table_name="skills")
    op.drop_table("skills")

    op.drop_index("ix_skill_types_is_active", table_name="skill_types")
    op.drop_index("ix_skill_types_code_unique", table_name="skill_types")
    op.drop_table("skill_types")
