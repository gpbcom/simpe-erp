from __future__ import annotations

# Standard library imports
from pathlib import Path
from typing import List, Tuple

# Third-party imports
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import Engine, create_engine, text

BACKEND_ROOT = Path(__file__).resolve().parents[2]

#: Every table here declares NOT NULL timestamps with no server default, so a
#: raw insert has to supply them. The value is arbitrary; only its presence
#: matters to this test.
STAMP = "'2026-01-01 00:00:00', '2026-01-01 00:00:00'"


class TestMigration0009Backfill:
    """Tests that moving the VAT category onto quote lines keeps the old tax.

    Notes:
        **The schema tests do not cover this.** They compare the migrated
        schema against the ORM metadata, which proves the column exists and is
        ``NOT NULL`` — and would pass just as happily if the backfill copied
        nothing and every existing line came out as ``necessity``.

        What that would mean is comfort care, quoted and issued at 20%, being
        re-read at 5.5% the next time anything recomputed a total. A customer
        is never re-billed for work already quoted, so the backfill is the
        promise this migration rests on, and it is asserted here against real
        rows.
    """

    def _engine_upgraded_to(self, database_path: Path, stop_after: str) -> Engine:
        """Migrate a scratch database up to and including one revision.

        Args:
            database_path (Path): Where to create the database.
            stop_after (str): The last revision to apply.

        Returns:
            Engine: An engine pointing at the migrated database.

        Notes:
            Revisions are driven directly rather than through
            ``command.upgrade`` so this needs no application configuration, no
            PostgreSQL URL and no password — the same approach the schema
            tests take.
        """
        config = Config()
        config.set_main_option(
            "script_location", str(BACKEND_ROOT / "conf" / "alembic")
        )
        script = ScriptDirectory.from_config(config)
        engine = create_engine(f"sqlite:///{database_path}")
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                for revision in reversed(
                    list(script.walk_revisions(base="base", head="heads"))
                ):
                    revision.module.upgrade()
                    if revision.revision == stop_after:
                        break
        return engine

    def _seed_a_quote_line(
        self, engine: Engine, catalog_category: str, line_id: str = "line-1"
    ) -> None:
        """Insert one company, customer, quote, catalog entry and quote line.

        Args:
            engine (Engine): The database to write to.
            catalog_category (str): The category on the catalog entry, which is
                where the VAT rate lived before this migration.
            line_id (str): The quote line's identifier.

        Notes:
            The columns are those revision 0008 actually leaves behind, which
            is not the same set the ORM declares today — multi-tenancy reached
            these tables later. Writing what the ORM says would insert columns
            that do not exist yet, and the error would look like a bug in the
            migration under test.

            Written as raw SQL rather than through the ORM. The ORM row already
            declares ``service_category``, so using it would insert the column
            this test is checking the migration adds — and the test would pass
            without the backfill ever running.
        """
        suffix = line_id
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO intervention_types (id, name, code, "
                    "service_category, is_active, created_at, updated_at) "
                    f"VALUES ('t-{suffix}', 'Service {suffix}', "
                    f"'CODE{suffix}', '{catalog_category}', 1, {STAMP})"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO customers (id, first_name, last_name, "
                    "phone_number, email, street, postal_code, city, country, "
                    "registration_status, created_at, updated_at) VALUES "
                    "('cu1', 'Marie', 'Durand', '+33612345678', "
                    "'marie@example.fr', '1 rue', '75004', 'Paris', 'France', "
                    f"'active', {STAMP})"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO quotes (id, reference, customer_id, status, "
                    f"created_at, updated_at) VALUES ('q1', 'DEV-1', 'cu1', "
                    f"'sent', {STAMP})"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO quote_lines (id, quote_id, position, name, "
                    "intervention_type_id, service_date, earliest_start, "
                    "latest_end, duration_minutes) "
                    f"VALUES ('{line_id}', 'q1', 0, 'Aide', 't-{suffix}', "
                    "'2026-09-01', '09:00:00', '12:00:00', 120)"
                )
            )

    def _categories(self, engine: Engine) -> List[Tuple[str, str]]:
        """Return every quote line's identifier and category.

        Args:
            engine (Engine): The database to read.

        Returns:
            List[Tuple[str, str]]: One pair per line.
        """
        with engine.connect() as connection:
            return [
                (row[0], row[1])
                for row in connection.execute(
                    text("SELECT id, service_category FROM quote_lines ORDER BY id")
                )
            ]

    def _run_0009(self, engine: Engine) -> None:
        """Apply revision 0009 to an already-migrated database.

        Args:
            engine (Engine): The database to upgrade.
        """
        config = Config()
        config.set_main_option(
            "script_location", str(BACKEND_ROOT / "conf" / "alembic")
        )
        script = ScriptDirectory.from_config(config)
        revision = next(
            entry
            for entry in script.walk_revisions(base="base", head="heads")
            if entry.revision == "0009"
        )
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                revision.module.upgrade()

    @pytest.mark.parametrize("category", ["necessity", "comfort"])
    def test_a_line_keeps_the_tax_it_was_quoted_at(
        self, tmp_path: Path, category: str
    ) -> None:
        """**The promise: no issued quote changes its total.**

        Args:
            tmp_path (Path): Scratch directory.
            category (str): The category on the catalog entry.

        Notes:
            ``comfort`` is the case that matters. A backfill that copied
            nothing would leave every line at the ``necessity`` default, and a
            quote issued at 20% would be re-read at 5.5% — the agency would
            owe the difference, and nothing on screen would say so.
        """
        engine = self._engine_upgraded_to(tmp_path / "before.db", stop_after="0008")
        self._seed_a_quote_line(engine, catalog_category=category)

        self._run_0009(engine)

        assert self._categories(engine) == [("line-1", category)]

    def test_each_line_follows_its_own_catalog_entry(self, tmp_path: Path) -> None:
        """Two lines, two entries, two different rates.

        Notes:
            A backfill written as a single `UPDATE ... SET x = <one value>`
            would pass the test above on whichever category it happened to
            pick. This one only passes if the update correlates each line with
            the entry it actually sells.
        """
        engine = self._engine_upgraded_to(tmp_path / "before.db", stop_after="0008")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO customers (id, first_name, last_name, "
                    "phone_number, email, street, postal_code, city, country, "
                    "registration_status, created_at, updated_at) VALUES "
                    "('cu1', 'Marie', 'Durand', '+33612345678', "
                    "'marie@example.fr', '1 rue', '75004', 'Paris', 'France', "
                    f"'active', {STAMP})"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO quotes (id, reference, customer_id, status, "
                    f"created_at, updated_at) VALUES ('q1', 'DEV-1', 'cu1', "
                    f"'sent', {STAMP})"
                )
            )
            for index, category in enumerate(("necessity", "comfort")):
                connection.execute(
                    text(
                        "INSERT INTO intervention_types (id, name, code, "
                        "service_category, is_active, created_at, updated_at) "
                        f"VALUES ('t{index}', 'Service {index}', 'C{index}', "
                        f"'{category}', 1, {STAMP})"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO quote_lines (id, quote_id, position, name, "
                        "intervention_type_id, service_date, earliest_start, "
                        "latest_end, duration_minutes) VALUES "
                        f"('line-{index}', 'q1', {index}, 'Aide', 't{index}', "
                        "'2026-09-01', '09:00:00', '12:00:00', 120)"
                    )
                )

        self._run_0009(engine)

        assert self._categories(engine) == [
            ("line-0", "necessity"),
            ("line-1", "comfort"),
        ]

    def test_the_column_is_required_afterwards(self, tmp_path: Path) -> None:
        """A line written after the migration must state its own category.

        Notes:
            This is why the migration adds the column nullable, backfills, and
            only then tightens it. Adding it ``NOT NULL`` outright fails on any
            table holding rows, and this one holds every quote line the agency
            has ever written.
        """
        engine = self._engine_upgraded_to(tmp_path / "before.db", stop_after="0008")
        self._seed_a_quote_line(engine, catalog_category="comfort")
        self._run_0009(engine)

        with pytest.raises(Exception):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO quote_lines (id, quote_id, position, name, "
                        "intervention_type_id, service_date, earliest_start, "
                        "latest_end, duration_minutes) VALUES "
                        "('line-2', 'q1', 1, 'Aide', 't-line-1', '2026-09-01', "
                        "'09:00:00', '12:00:00', 120)"
                    )
                )

    def test_an_empty_table_migrates_cleanly(self, tmp_path: Path) -> None:
        """A fresh install has nothing to backfill and must not fail on it."""
        engine = self._engine_upgraded_to(tmp_path / "before.db", stop_after="0008")

        self._run_0009(engine)

        assert self._categories(engine) == []
