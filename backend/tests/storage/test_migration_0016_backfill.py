from __future__ import annotations

# Standard library imports
from pathlib import Path
from typing import List, Optional, Tuple

# Third-party imports
import pytest
from sqlalchemy import Engine, text

# First-party imports
from migration_templates import MigrationTemplates

#: Every table here declares NOT NULL timestamps with no server default, so a
#: raw insert has to supply them. The value is arbitrary; only its presence
#: matters to these tests.
STAMP = "'2026-01-01 00:00:00', '2026-01-01 00:00:00'"


class TestMigration0016Backfill:
    """Tests that every existing quote, run and visit lands in the right agency.

    Notes:
        **The schema tests do not cover this.** They compare the migrated schema
        against the ORM metadata, which proves the three columns exist and are
        ``NOT NULL`` — and would pass just as happily if every row had been
        filed under one arbitrary agency.

        That would not be quiet for long. The column decides whose accepted work
        a planning run schedules and whose calendar it rewrites, so a quote filed
        under the wrong agency is one that agency's assistants are sent out to
        deliver.
    """

    ############################
    # Internal Helpers Methods #
    ############################

    def _seed_company(self, engine: Engine, company_id: str, name: str) -> None:
        """Insert one agency.

        Args:
            engine (Engine): The database to write to.
            company_id (str): The agency's identifier.
            name (str): Its display name, which is unique.
        """
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO companies (id, name, "
                    "registration_number, is_accepting_applications, "
                    f"created_at, updated_at) VALUES ('{company_id}', '{name}', "
                    f"'RCS-{company_id}', 1, {STAMP})"
                )
            )

    def _seed_user(self, engine: Engine, user_id: str, company_id: str) -> None:
        """Insert one account belonging to an agency.

        Args:
            engine (Engine): The database to write to.
            user_id (str): The account's identifier.
            company_id (str): The agency it belongs to.
        """
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, email, first_name, last_name, "
                    "hashed_password, role, is_active, company_id, "
                    "account_origin, must_change_password, language, "
                    f"created_at, updated_at) VALUES ('{user_id}', "
                    f"'{user_id}@example.fr', 'Luc', 'Martin', 'x', 'admin', 1, "
                    f"'{company_id}', 'created-by-staff', 0, 'fr', {STAMP})"
                )
            )

    def _seed_quote(
        self, engine: Engine, quote_id: str, author_id: Optional[str]
    ) -> None:
        """Insert one quote as revision 0015 leaves it: with no agency of its own.

        Args:
            engine (Engine): The database to write to.
            quote_id (str): The quote's identifier.
            author_id (Optional[str]): The account that wrote it, or ``None``
                for a quote whose author has since been deleted.

        Notes:
            Raw SQL rather than the ORM, and a customer inserted alongside
            because the quote's foreign key requires one. The ORM row already
            declares ``company_id``, so inserting through it would supply the
            very column this test checks the migration adds.
        """
        author = f"'{author_id}'" if author_id else "NULL"
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO customers (id, first_name, "
                    "last_name, phone_number, street, postal_code, city, "
                    f"country, registration_status, created_at, updated_at) "
                    f"VALUES ('cust1', 'Anne', 'Durand', '+33612345678', "
                    f"'1 rue de Paris', '75001', 'Paris', 'France', 'active', "
                    f"{STAMP})"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO quotes (id, reference, customer_id, status, "
                    "authored_by, auto_renew, created_at, updated_at) VALUES "
                    f"('{quote_id}', 'D-{quote_id}', 'cust1', 'accepted', "
                    f"{author}, 0, {STAMP})"
                )
            )

    def _seed_run(self, engine: Engine, run_id: str, requested_by: str) -> None:
        """Insert one planning run with no agency of its own.

        Args:
            engine (Engine): The database to write to.
            run_id (str): The run's identifier.
            requested_by (str): The account that asked for it.
        """
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO planning_runs (id, status, requested_by, "
                    "period_start, period_end) VALUES "
                    f"('{run_id}', 'succeeded', '{requested_by}', "
                    f"'2026-08-03', '2026-08-09')"
                )
            )

    def _agencies(self, engine: Engine, table: str) -> List[Tuple[str, str]]:
        """Return each row's identifier and the agency it was filed under.

        Args:
            engine (Engine): The database to read.
            table (str): The table to read from.

        Returns:
            List[Tuple[str, str]]: One pair per row, ordered by identifier.
        """
        with engine.connect() as connection:
            return [
                (row[0], row[1])
                for row in connection.execute(
                    text(f"SELECT id, company_id FROM {table} ORDER BY id")  # noqa: S608
                )
            ]

    ############################
    # Publicly Exposed Methods #
    ############################

    def test_a_quote_follows_its_author(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """**The promise: nobody's quote moves agency on deployment.**

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            The agency was reachable through the author's account and nowhere
            else, so that is the path the backfill follows while it still holds.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0015")
        self._seed_company(engine, "co1", "Agency One")
        self._seed_company(engine, "co2", "Agency Two")
        self._seed_user(engine, "user-1", "co2")
        self._seed_quote(engine, "quote-1", author_id="user-1")

        migrations.apply(engine, "0016")

        assert self._agencies(engine, "quotes") == [("quote-1", "co2")]

    def test_a_run_follows_its_requester(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """A run is filed under the agency of whoever asked for it.

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0015")
        self._seed_company(engine, "co1", "Agency One")
        self._seed_company(engine, "co2", "Agency Two")
        self._seed_user(engine, "user-1", "co2")
        self._seed_run(engine, "run-1", requested_by="user-1")

        migrations.apply(engine, "0016")

        assert self._agencies(engine, "planning_runs") == [("run-1", "co2")]

    def test_an_orphaned_quote_falls_back_to_the_only_agency(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """A quote whose author has gone is still filed somewhere.

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            ``authored_by`` is nullable on purpose — an author who leaves must
            not take their quotes with them — so the join the backfill follows
            can come up empty. With one agency in the database there is an
            unambiguous answer, and every deployment today has exactly one.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0015")
        self._seed_company(engine, "co1", "Agency One")
        self._seed_quote(engine, "quote-1", author_id=None)

        migrations.apply(engine, "0016")

        assert self._agencies(engine, "quotes") == [("quote-1", "co1")]

    def test_an_orphan_with_several_agencies_refuses_to_guess(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """**Refusing is the point.**

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            Guessing would file a quote under an agency that never wrote it, and
            the next planning run would schedule its visits and send that
            agency's assistants to deliver them. A migration that stops, naming
            the problem, is recoverable; a deployment that silently rehomed
            somebody's commercial history is not.

            This mirrors the policy migration 0008 set for the same situation.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0015")
        self._seed_company(engine, "co1", "Agency One")
        self._seed_company(engine, "co2", "Agency Two")
        self._seed_quote(engine, "quote-1", author_id=None)

        with pytest.raises(RuntimeError, match="no agency"):
            migrations.apply(engine, "0016")

    def test_an_empty_database_migrates_cleanly(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """A fresh install has nothing to backfill and no agency to demand.

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            Worth its own test because the refusal above keys off "there are
            orphans and no single agency" — and a brand-new database satisfies
            the second half of that. Reading it as a failure would break every
            first deployment.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0015")

        migrations.apply(engine, "0016")

        assert self._agencies(engine, "quotes") == []
