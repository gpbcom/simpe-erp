"""A company has places, the places have teams, and the planner works per team.

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-12

Notes:
    Five tables and three columns, together, because they are one statement
    about the business: a company operates from several **sites**, each site has
    **teams**, every person belongs to one of each, and a planning is computed
    for a team rather than for the whole workforce.

    **The backfill is not optional, and it is the reason this migration is one
    revision rather than three.** Quote creation now refuses when no team can be
    determined, and the planner reads ``quotes.team_id`` to decide what to
    schedule — so a deployment that gained the columns without the rows could
    not write a quote and would plan nothing. Every existing company therefore
    ends this migration with a head office, a team, every one of its people in
    both, and every quote, run and visit filed under that team.

    The head office **copies the company's whole record** — its address and
    coordinate, and its legal identity with it. The coordinate is what makes the
    closest-team rule work on the first quote written after the upgrade. A site
    with no coordinate cannot win a distance contest, so an empty address would
    send every quote down the busyness fallback and make the feature look broken
    on day one. The legal identity is copied because an ``Agency`` *is* a
    ``Company`` in the model: the head office is where the business is
    registered, and a head office that carried none of it would print a quote
    with no SIRET and no bank details.

    Where 0016 could follow a nullable path to find each row's agency, there is
    no such path here — nothing in the old schema knows about teams. So the fill
    is uniform: one team per company, everybody on it. Placing only *some* of
    the workforce would blank most of the calendar on the first run after
    deployment, which is the failure this migration exists to avoid rather than
    cause.

    **``manager_user_id`` refuses to guess.** A company with no manager and no
    administrator gets a ``RuntimeError`` naming it, following the policy 0008
    and 0016 set: a team whose manager is somebody arbitrary is a team that
    hands one person's re-plan button to another.
"""

from __future__ import annotations

# Standard library imports
from typing import Optional, Sequence, Union
from uuid import NAMESPACE_URL, uuid5

# Third-party imports
from alembic import op
import sqlalchemy as sa

revision: str = "0028"
down_revision: Optional[str] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Tables gaining a ``team_id`` column, in the order they are filled.
SCOPED_TABLES: tuple[str, ...] = ("quotes", "planning_runs", "interventions")

#: Namespace the derived identifiers hang off. Deriving rather than generating
#: is what lets this migration be reasoned about after the fact — the head
#: office of a known company has a known identifier — and it is the same
#: discipline the seeder follows, which is what stops the two creating a second
#: head office beside the one already there.
IDENTITY_NAMESPACE: str = "https://simple-erp.fr/migration/0028"

#: What the backfilled team is called. French, like every other seeded label,
#: and deliberately generic: it is the team an administrator will rename.
DEFAULT_TEAM_NAME: str = "Equipe principale"


def _derived_id(kind: str, key: str) -> str:
    """Return a stable identifier for a row this migration creates.

    Args:
        kind (str): What is being identified, such as ``"agency"``.
        key (str): The natural key, in practice the company identifier.

    Returns:
        str: A UUID5, identical on every run against the same database.
    """
    return str(uuid5(NAMESPACE_URL, f"{IDENTITY_NAMESPACE}/{kind}/{key}"))


def _manager_of(connection: sa.Connection, company_id: str) -> str:
    """Return the account that should run a company's backfilled team.

    Args:
        connection (sa.Connection): The open connection.
        company_id (str): The company whose team is being created.

    Returns:
        str: The account identifier.

    Raises:
        RuntimeError: If the company has neither a manager nor an
            administrator.

    Notes:
        A manager is preferred over an administrator, and the earliest of either
        over a later one, so the choice is deterministic rather than whichever
        row the database happened to return. An administrator is the fallback
        because a small agency often has no separate manager at all. Nobody at
        all is refused, because a team run by an arbitrary account is a team
        whose re-plan button belongs to the wrong person.
    """
    account = connection.execute(
        sa.text(
            "SELECT id FROM users "
            "WHERE company_id = :company_id AND role IN ('manager', 'admin') "
            "ORDER BY CASE role WHEN 'manager' THEN 0 ELSE 1 END, created_at ASC"
        ),
        {"company_id": company_id},
    ).scalar()
    if account is None:
        raise RuntimeError(
            f"Company {company_id!r} has no manager and no administrator, so "
            f"the team this migration creates for it would have nobody to run "
            f"it. Create a manager or an administrator for that company, then "
            f"run this migration again."
        )
    return str(account)


def _create_tables() -> None:
    """Create the five tables this revision introduces."""
    op.create_table(
        "agencies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(length=36),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("agency_type", sa.String(length=16), nullable=False),
        # The company's own columns. A site *is* a company in the model:
        # the head office is where the business is registered, and a quote
        # prints its SIRET and its bank details from the site it was
        # written at. Nullable, exactly as on ``companies``.
        sa.Column("legal_form", sa.String(length=64), nullable=True),
        sa.Column("share_capital", sa.Numeric(14, 2), nullable=True),
        sa.Column("rcs_number", sa.String(length=64), nullable=True),
        sa.Column("vat_number", sa.String(length=20), nullable=True),
        sa.Column("sap_declaration_number", sa.String(length=64), nullable=True),
        sa.Column("phone_number", sa.String(length=64), nullable=True),
        sa.Column("registration_number", sa.String(length=64), nullable=True),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("iban", sa.String(length=34), nullable=True),
        sa.Column("bic", sa.String(length=11), nullable=True),
        sa.Column("logo_url", sa.String(length=512), nullable=True),
        sa.Column("is_accepting_applications", sa.Boolean(), nullable=False),
        sa.Column("street", sa.String(length=255), nullable=True),
        sa.Column("postal_code", sa.String(length=16), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("geocoding_error", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agencies_company", "agencies", ["company_id"])
    op.create_index(
        "uq_agencies_company_name", "agencies", ["company_id", "name"], unique=True
    )
    # Partial, so "one head office per company" is a fact of the database. The
    # predicate is spelled for both engines because the suite runs on SQLite and
    # the deployment on PostgreSQL, and an invariant that holds in only one of
    # them is an invariant the tests cannot prove.
    op.create_index(
        "uq_agencies_company_hq",
        "agencies",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("agency_type = 'hq'"),
        sqlite_where=sa.text("agency_type = 'hq'"),
    )

    op.create_table(
        "agency_members",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "agency_id",
            sa.String(length=36),
            sa.ForeignKey("agencies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("member_kind", sa.String(length=8), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agency_members_agency", "agency_members", ["agency_id"])
    op.create_index(
        "uq_agency_members_member",
        "agency_members",
        ["member_kind", "member_id"],
        unique=True,
    )

    op.create_table(
        "teams",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(length=36),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "agency_id",
            sa.String(length=36),
            sa.ForeignKey("agencies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "manager_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_teams_company", "teams", ["company_id"])
    op.create_index("ix_teams_agency", "teams", ["agency_id"])
    op.create_index("ix_teams_manager", "teams", ["manager_user_id"])
    op.create_index(
        "uq_teams_company_name", "teams", ["company_id", "name"], unique=True
    )

    op.create_table(
        "team_members",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "team_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("member_kind", sa.String(length=8), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_team_members_team", "team_members", ["team_id"])
    op.create_index(
        "uq_team_members_member",
        "team_members",
        ["member_kind", "member_id"],
        unique=True,
    )

    op.create_table(
        "team_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "team_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("document_key", sa.String(length=512), nullable=False),
        sa.Column("uploaded_by", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by_name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_team_documents_team", "team_documents", ["team_id", "created_at"]
    )


def _backfill(connection: sa.Connection) -> None:
    """Give every existing company a head office, a team and its people.

    Args:
        connection (sa.Connection): The open connection.

    Raises:
        RuntimeError: If a company has nobody who could run its team.
    """
    companies = connection.execute(
        sa.text(
            "SELECT id, name, legal_form, share_capital, rcs_number, "
            "vat_number, sap_declaration_number, phone_number, "
            "registration_number, contact_email, iban, bic, logo_url, "
            "is_accepting_applications, street, postal_code, city, country, "
            "latitude, longitude, geocoding_error "
            "FROM companies ORDER BY created_at ASC"
        )
    ).all()
    for company in companies:
        company_id = str(company.id)
        agency_id = _derived_id("agency", company_id)
        team_id = _derived_id("team", company_id)
        manager_id = _manager_of(connection, company_id)

        connection.execute(
            sa.text(
                "INSERT INTO agencies (id, company_id, name, agency_type, "
                "legal_form, share_capital, rcs_number, vat_number, "
                "sap_declaration_number, phone_number, registration_number, "
                "contact_email, iban, bic, logo_url, "
                "is_accepting_applications, street, postal_code, city, "
                "country, latitude, longitude, geocoding_error, created_at, "
                "updated_at) VALUES "
                "(:id, :company_id, :name, 'hq', :legal_form, :share_capital, "
                ":rcs_number, :vat_number, :sap_declaration_number, "
                ":phone_number, :registration_number, :contact_email, :iban, "
                ":bic, :logo_url, :is_accepting_applications, :street, "
                ":postal_code, :city, :country, :latitude, :longitude, "
                ":geocoding_error, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": agency_id,
                "company_id": company_id,
                "name": company.name,
                "legal_form": company.legal_form,
                "share_capital": company.share_capital,
                "rcs_number": company.rcs_number,
                "vat_number": company.vat_number,
                "sap_declaration_number": company.sap_declaration_number,
                "phone_number": company.phone_number,
                "registration_number": company.registration_number,
                "contact_email": company.contact_email,
                "iban": company.iban,
                "bic": company.bic,
                "logo_url": company.logo_url,
                "is_accepting_applications": company.is_accepting_applications,
                "street": company.street,
                "postal_code": company.postal_code,
                "city": company.city,
                "country": company.country,
                "latitude": company.latitude,
                "longitude": company.longitude,
                "geocoding_error": company.geocoding_error,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO teams (id, company_id, agency_id, name, "
                "manager_user_id, created_at, updated_at) VALUES "
                "(:id, :company_id, :agency_id, :name, :manager_user_id, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": team_id,
                "company_id": company_id,
                "agency_id": agency_id,
                "name": DEFAULT_TEAM_NAME,
                "manager_user_id": manager_id,
            },
        )

        # Everybody, not a subset. The planner's workforce has to come out of
        # this migration identical to what it was before it, or the first run
        # after deployment blanks most of the calendar.
        for kind, table in (("user", "users"), ("hca", "hcas")):
            people = (
                connection.execute(
                    sa.text(
                        f"SELECT id FROM {table} "  # noqa: S608
                        f"WHERE company_id = :company_id ORDER BY id ASC"
                    ),
                    {"company_id": company_id},
                )
                .scalars()
                .all()
            )
            for person_id in people:
                for membership_table, owner_column, owner_id in (
                    ("agency_members", "agency_id", agency_id),
                    ("team_members", "team_id", team_id),
                ):
                    connection.execute(
                        sa.text(
                            f"INSERT INTO {membership_table} "  # noqa: S608
                            f"(id, {owner_column}, member_kind, member_id, "
                            f"created_at) VALUES (:id, :owner_id, :member_kind, "
                            f":member_id, CURRENT_TIMESTAMP)"
                        ),
                        {
                            "id": _derived_id(membership_table, f"{kind}/{person_id}"),
                            "owner_id": owner_id,
                            "member_kind": kind,
                            "member_id": str(person_id),
                        },
                    )

        for table in SCOPED_TABLES:
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET team_id = :team_id "  # noqa: S608
                    f"WHERE company_id = :company_id AND team_id IS NULL"
                ),
                {"team_id": team_id, "company_id": company_id},
            )


def _orphan_count(connection: sa.Connection) -> int:
    """Return how many scoped rows still name no team.

    Args:
        connection (sa.Connection): The open connection.

    Returns:
        int: The total across the three scoped tables.
    """
    return sum(
        connection.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE team_id IS NULL")  # noqa: S608
        ).scalar_one()
        for table in SCOPED_TABLES
    )


def upgrade() -> None:
    """Create the tables, add the columns, fill them, then close them.

    Raises:
        RuntimeError: If a company has nobody who could run its team, or if a
            quote, run or visit is left naming no team.
    """
    _create_tables()

    for table in SCOPED_TABLES:
        op.add_column(table, sa.Column("team_id", sa.String(length=36), nullable=True))

    connection = op.get_bind()
    _backfill(connection)

    orphans = _orphan_count(connection)
    if orphans:
        raise RuntimeError(
            f"{orphans} row(s) across {', '.join(SCOPED_TABLES)} still name no "
            f"team after the backfill, which means they name a company that "
            f"does not exist. A quote with no team is never planned and a visit "
            f"with no team escapes every re-plan, so this is refused rather "
            f"than stored. Repair those rows' company_id, then run this "
            f"migration again."
        )

    for table in SCOPED_TABLES:
        # Batch mode, because the migration test runs against SQLite and SQLite
        # has no ALTER COLUMN. On PostgreSQL this emits the plain ALTER; on
        # SQLite Alembic rebuilds the table around the new constraint.
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "team_id", existing_type=sa.String(length=36), nullable=False
            )

    op.create_index("ix_quotes_team_status", "quotes", ["team_id", "status"])
    op.create_index(
        "ix_planning_runs_team", "planning_runs", ["team_id", "period_start"]
    )
    op.create_index("ix_interventions_team_day", "interventions", ["team_id", "day"])


def downgrade() -> None:
    """Drop the columns and the five tables.

    Notes:
        The organisation goes, and with it every team assignment. No business
        data is lost — the quotes, the runs and the visits all survive, and
        their company scoping is untouched — but which team delivered what
        cannot be recovered by upgrading again: the fill would put everybody
        back on one team per company, and a deployment that had split into
        several would have to rebuild them by hand.
    """
    op.drop_index("ix_interventions_team_day", table_name="interventions")
    op.drop_index("ix_planning_runs_team", table_name="planning_runs")
    op.drop_index("ix_quotes_team_status", table_name="quotes")
    for table in SCOPED_TABLES:
        op.drop_column(table, "team_id")

    op.drop_index("ix_team_documents_team", table_name="team_documents")
    op.drop_table("team_documents")
    op.drop_index("uq_team_members_member", table_name="team_members")
    op.drop_index("ix_team_members_team", table_name="team_members")
    op.drop_table("team_members")
    op.drop_index("uq_teams_company_name", table_name="teams")
    op.drop_index("ix_teams_manager", table_name="teams")
    op.drop_index("ix_teams_agency", table_name="teams")
    op.drop_index("ix_teams_company", table_name="teams")
    op.drop_table("teams")
    op.drop_index("uq_agency_members_member", table_name="agency_members")
    op.drop_index("ix_agency_members_agency", table_name="agency_members")
    op.drop_table("agency_members")
    op.drop_index("uq_agencies_company_hq", table_name="agencies")
    op.drop_index("uq_agencies_company_name", table_name="agencies")
    op.drop_index("ix_agencies_company", table_name="agencies")
    op.drop_table("agencies")
