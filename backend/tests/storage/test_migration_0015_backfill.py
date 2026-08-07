from __future__ import annotations

# Standard library imports
from pathlib import Path
from typing import List, Tuple

# Third-party imports
from sqlalchemy import Engine, text

# First-party imports
from migration_templates import MigrationTemplates
from models.enums import Language

#: Every table here declares NOT NULL timestamps with no server default, so a
#: raw insert has to supply them. The value is arbitrary; only its presence
#: matters to this test.
STAMP = "'2026-01-01 00:00:00', '2026-01-01 00:00:00'"


class TestMigration0015Backfill:
    """Tests that giving accounts a language leaves every existing one French.

    Notes:
        **The schema tests do not cover this.** They compare the migrated
        schema against the ORM metadata, which proves the column exists and is
        ``NOT NULL`` — and would pass just as happily if every existing account
        were backfilled with English, or with an empty string that the model
        then refuses to read.

        Either would be quiet. The column decides what language the quotes
        emailed to customers come out in, so an English backfill would send
        every French agency's customers an English document on the deployment
        that was only supposed to make the setting reachable.
    """

    ############################
    # Internal Helpers Methods #
    ############################

    def _seed_an_account(self, engine: Engine, user_id: str = "user-1") -> None:
        """Insert one company and one account as revision 0014 leaves them.

        Args:
            engine (Engine): The database to write to.
            user_id (str): The account's identifier.

        Notes:
            Raw SQL rather than the ORM. The ORM row already declares
            ``language``, so inserting through it would supply the very column
            this test checks the migration adds — and the test would pass
            without the backfill ever running.
        """
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO companies (id, name, "
                    "registration_number, is_accepting_applications, "
                    f"created_at, updated_at) VALUES ('co1', 'Agency', 'RCS1', "
                    f"1, {STAMP})"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO users (id, email, first_name, last_name, "
                    "hashed_password, role, is_active, company_id, "
                    "account_origin, must_change_password, created_at, "
                    f"updated_at) VALUES ('{user_id}', '{user_id}@example.fr', "
                    f"'Luc', 'Martin', 'x', 'admin', 1, 'co1', "
                    f"'created-by-staff', 0, {STAMP})"
                )
            )

    def _languages(self, engine: Engine) -> List[Tuple[str, str]]:
        """Return every account's identifier and stored language.

        Args:
            engine (Engine): The database to read.

        Returns:
            List[Tuple[str, str]]: One pair per account.
        """
        with engine.connect() as connection:
            return [
                (row[0], row[1])
                for row in connection.execute(
                    text("SELECT id, language FROM users ORDER BY id")
                )
            ]

    ############################
    # Publicly Exposed Methods #
    ############################

    def test_an_existing_account_is_backfilled_french(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """**The promise: nobody's documents change language on deployment.**

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            The preference lived in the browser until this revision, so the
            migration cannot see what anybody had chosen. French is what the
            agency, its contract types and its holidays are, which makes it the
            safe reading rather than merely the common one.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0014")
        self._seed_an_account(engine)

        migrations.apply(engine, "0015")

        assert self._languages(engine) == [("user-1", "fr")]

    def test_every_existing_account_is_backfilled(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """The backfill reaches every row, not just the first.

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0014")
        for index in range(3):
            self._seed_an_account(engine, user_id=f"user-{index}")

        migrations.apply(engine, "0015")

        stored = self._languages(engine)
        assert len(stored) == 3
        assert {language for _, language in stored} == {"fr"}

    def test_the_backfilled_value_is_one_the_model_accepts(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """What the migration wrote is a language the enum can parse.

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            A backfill of ``'french'`` or ``'FR'`` would satisfy the column's
            ``NOT NULL`` and then raise on the first read of the row — a long
            way from the migration that caused it.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0014")
        self._seed_an_account(engine)

        migrations.apply(engine, "0015")

        assert Language(self._languages(engine)[0][1]) is Language.FR
