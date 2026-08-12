from __future__ import annotations

# Standard library imports
from pathlib import Path
from typing import List, Tuple

# Third-party imports
import pytest
from sqlalchemy import Engine, text

# First-party imports
from migration_templates import MigrationTemplates

BACKEND_ROOT = Path(__file__).resolve().parents[2]

#: Every table here declares NOT NULL timestamps with no server default, so a
#: raw insert has to supply them. The value is arbitrary; only its presence
#: matters to this test.
STAMP = "'2026-01-01 00:00:00', '2026-01-01 00:00:00'"

#: ``hcas.working_weekdays`` arrived NOT NULL in 0013 with its server default
#: dropped afterwards, so a raw insert has to supply one. The value is
#: immaterial here — this suite is about the organisation, not the rota.
WORKING_WEEK = "monday,tuesday,wednesday,thursday,friday"


class TestMigration0028Backfill:
    """Tests that gaining an organisation costs no company its calendar.

    Notes:
        **The schema tests do not cover this.** They compare the migrated
        schema against the ORM metadata, which proves the five tables and the
        three ``team_id`` columns exist and are ``NOT NULL`` — and would pass
        just as happily if not one row had been written into them.

        Every one of those omissions is silent and severe. A company with no
        head office cannot have a team; a team with nobody on it gives the
        planner an empty workforce, so the first run after deployment leaves
        every visit unplaced; and a quote with no ``team_id`` is one no run ever
        reads, so a family simply stops being visited with nothing on any screen
        saying why.

        So this asserts the four steps of the backfill against real rows: the
        head office and its copied coordinate, the team and its manager, both
        membership tables, and the three scoped tables.
    """

    ############################
    # Internal Helpers Methods #
    ############################

    def _seed_a_company(self, engine: Engine) -> None:
        """Insert a company, its staff and its work as 0027 leaves them.

        Args:
            engine (Engine): The database to write to.

        Notes:
            Raw SQL rather than the ORM, for the reason the 0013 suite gives:
            the ORM rows already declare ``team_id``, so inserting through them
            would supply the very column this test checks the migration fills.
        """
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO companies (id, name, registration_number, "
                    "street, postal_code, city, country, latitude, longitude, "
                    "is_accepting_applications, created_at, updated_at) VALUES "
                    "('co1', 'Aide et Presence', 'RCS1', '10 rue de la "
                    "Roquette', '75011', 'Paris', 'France', 48.8551, 2.3720, "
                    f"1, {STAMP})"
                )
            )
            # An assistant record, and two accounts: one administrator and one
            # manager. The manager is the one the migration must pick.
            connection.execute(
                text(
                    "INSERT INTO hcas (id, first_name, last_name, phone_number, "
                    "email, street, postal_code, city, country, company_id, "
                    "contract_type, field_employee, working_weekdays, "
                    "created_at, updated_at) VALUES ('hca-1', 'Luc', 'Martin', "
                    "'+33612345678', 'luc@example.fr', '1 rue', '75001', "
                    f"'Paris', 'France', 'co1', 'cdi', 1, '{WORKING_WEEK}', "
                    f"{STAMP})"
                )
            )
            for user_id, role, stamp in (
                ("user-admin", "admin", "'2026-01-01 00:00:00'"),
                ("user-manager", "manager", "'2026-01-02 00:00:00'"),
            ):
                connection.execute(
                    text(
                        "INSERT INTO users (id, first_name, last_name, email, "
                        "hashed_password, role, is_active, company_id, "
                        "account_origin, language, must_change_password, "
                        "created_at, updated_at) VALUES "
                        f"('{user_id}', 'A', 'B', '{user_id}@example.fr', "
                        f"'x', '{role}', 1, 'co1', 'created-by-staff', 'fr', 0, "
                        f"{stamp}, {stamp})"
                    )
                )
            connection.execute(
                text(
                    "INSERT INTO customers (id, first_name, last_name, "
                    "phone_number, email, street, postal_code, city, country, "
                    "registration_status, created_at, updated_at) VALUES "
                    "('cust-1', 'Jeanne', 'Vincent', '+33612345679', "
                    "'jeanne@example.fr', '2 rue', '75002', 'Paris', 'France', "
                    f"'active', {STAMP})"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO quotes (id, company_id, reference, "
                    "customer_id, status, auto_renew, created_at, updated_at) "
                    "VALUES ('quote-1', 'co1', 'D-1', 'cust-1', 'accepted', 0, "
                    f"{STAMP})"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO planning_runs (id, status, company_id, "
                    "requested_by, period_start, period_end) VALUES "
                    "('run-1', 'succeeded', 'co1', 'user-admin', '2026-02-02', "
                    "'2026-02-06')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO interventions (id, planning_run_id, "
                    "company_id, name, intervention_type_id, quote_line_id, "
                    "hca_id, hca_full_name, customer_id, day, start_time, "
                    "end_time, street, postal_code, city, country, status) "
                    "VALUES ('visit-1', 'run-1', 'co1', 'Toilette', 'type-1', "
                    "'line-1', 'hca-1', 'Luc Martin', 'cust-1', '2026-02-02', "
                    "'09:00:00', '10:00:00', '2 rue', '75002', 'Paris', "
                    "'France', 'planned')"
                )
            )

    def _rows(self, engine: Engine, statement: str) -> List[Tuple[object, ...]]:
        """Return every row a statement yields.

        Args:
            engine (Engine): The database to read.
            statement (str): The statement to run.

        Returns:
            List[Tuple[object, ...]]: The rows, as tuples.
        """
        with engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(statement))]

    ############################
    # Publicly Exposed Methods #
    ############################

    def test_the_company_gains_a_head_office_carrying_its_coordinate(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """**The promise: the closest-team rule works on the first quote.**

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            The coordinate is the half that matters. A head office created with
            a name and no point cannot win a distance contest, so every quote
            written after the upgrade would fall through to the busyness
            tie-break — which looks exactly like the proximity rule not working.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0027")
        self._seed_a_company(engine)

        migrations.apply(engine, "0028")

        agencies = self._rows(
            engine,
            "SELECT company_id, name, agency_type, street, latitude, longitude "
            "FROM agencies",
        )
        assert agencies == [
            ("co1", "Aide et Presence", "hq", "10 rue de la Roquette", 48.8551, 2.3720)
        ]

    def test_the_head_office_inherits_the_business_identity(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """**The promise: a quote written after the upgrade still prints a SIRET.**

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            An ``Agency`` *is* a ``Company``: the head office is where the
            business is registered, and the quote and invoice renderers print
            the registration number, the VAT number and the bank details from
            the site the document was written at. A head office backfilled with
            only a name and an address would send out documents missing every
            statutory mention, and nothing would fail — the papers would simply
            be wrong.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0027")
        self._seed_a_company(engine)

        migrations.apply(engine, "0028")

        identity = self._rows(
            engine,
            "SELECT registration_number, is_accepting_applications FROM agencies",
        )
        assert identity == [("RCS1", 1)]

    def test_the_company_gains_one_team_run_by_its_manager(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """A manager is preferred over an administrator, deterministically.

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            The fixture's administrator is the *earlier* account, so a fill that
            simply took the oldest staff member would pick them. Preferring the
            manager is what makes the re-plan button land with the person whose
            job it is.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0027")
        self._seed_a_company(engine)

        migrations.apply(engine, "0028")

        teams = self._rows(
            engine, "SELECT company_id, name, manager_user_id FROM teams"
        )
        assert teams == [("co1", "Equipe principale", "user-manager")]

        agency_id = self._rows(engine, "SELECT id FROM agencies")[0][0]
        assert self._rows(engine, "SELECT agency_id FROM teams") == [(agency_id,)]

    def test_every_person_joins_the_site_and_the_team(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """**Everybody, not a subset.**

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            The planner's workforce is the team's assistant records. Placing
            only some of them would blank most of the calendar on the first run
            after deployment, and the run would report the missing visits as
            unplaceable rather than as unstaffed.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0027")
        self._seed_a_company(engine)

        migrations.apply(engine, "0028")

        expected = [
            ("hca", "hca-1"),
            ("user", "user-admin"),
            ("user", "user-manager"),
        ]
        for table in ("agency_members", "team_members"):
            members = self._rows(
                engine,
                f"SELECT member_kind, member_id FROM {table} "  # noqa: S608
                f"ORDER BY member_kind, member_id",
            )
            assert members == expected, table

    def test_every_quote_run_and_visit_names_the_team(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """**The promise: nothing becomes invisible to the planner.**

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            A quote with no team is one no run ever reads, and a visit with no
            team escapes every re-plan for ever. Both are silent, which is why
            the migration refuses rather than leaving them.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0027")
        self._seed_a_company(engine)

        migrations.apply(engine, "0028")

        team_id = self._rows(engine, "SELECT id FROM teams")[0][0]
        for table in ("quotes", "planning_runs", "interventions"):
            scoped = self._rows(engine, f"SELECT team_id FROM {table}")  # noqa: S608
            assert scoped == [(team_id,)], table

    def test_a_company_with_nobody_to_run_a_team_is_refused(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """The migration refuses to guess, and says which company.

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            The policy migrations 0008 and 0016 set. A team run by an arbitrary
            account hands one person's re-plan button to another, and the wrong
            answer here is far harder to notice than a failed upgrade.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0027")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO companies (id, name, registration_number, "
                    "is_accepting_applications, created_at, updated_at) VALUES "
                    f"('co-empty', 'Sans personne', 'RCS9', 1, {STAMP})"
                )
            )

        with pytest.raises(RuntimeError, match="co-empty"):
            migrations.apply(engine, "0028")

    def test_a_second_head_office_is_refused_by_the_database(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """The partial unique index holds on SQLite as well as PostgreSQL.

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            Declared with both ``postgresql_where`` and ``sqlite_where``
            precisely so this assertion is possible: an invariant that holds
            only in the deployment engine is one the suite cannot prove, and the
            service's own refusal would then be the single point of failure.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0027")
        self._seed_a_company(engine)
        migrations.apply(engine, "0028")

        with pytest.raises(Exception, match="uq_agencies_company_hq|UNIQUE"):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO agencies (id, company_id, name, "
                        "agency_type, is_accepting_applications, created_at, "
                        f"updated_at) VALUES ('ag-2', 'co1', 'Second siege', "
                        f"'hq', 1, {STAMP})"
                    )
                )

    def test_a_person_cannot_be_on_two_teams(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """**The constraint the whole planning decomposition rests on.**

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            Two teams' runs each delete and rewrite their own days, so somebody
            on both would have two complete calendars written over the same week
            by two runs, neither of which clears the other's visits. They would
            be double-booked with nothing reporting it — which is why this is a
            unique index rather than a check in a service.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0027")
        self._seed_a_company(engine)
        migrations.apply(engine, "0028")

        agency_id = self._rows(engine, "SELECT id FROM agencies")[0][0]
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO teams (id, company_id, agency_id, name, "
                    "manager_user_id, created_at, updated_at) VALUES "
                    "('team-2', 'co1', :agency_id, 'Equipe Est', "
                    f"'user-manager', {STAMP})"
                ),
                {"agency_id": agency_id},
            )

        with pytest.raises(Exception, match="uq_team_members_member|UNIQUE"):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO team_members (id, team_id, member_kind, "
                        "member_id, created_at) VALUES ('tm-x', 'team-2', "
                        "'hca', 'hca-1', '2026-01-01 00:00:00')"
                    )
                )
