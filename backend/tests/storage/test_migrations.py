from __future__ import annotations

# Standard library imports
from pathlib import Path
from typing import Dict, List, Tuple

from alembic.config import Config

# Third-party imports
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import Engine, create_engine, inspect

# First-party imports
from storage.orm import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]

ColumnSnapshot = Dict[str, Tuple[str, bool]]
ForeignKeySnapshot = List[Tuple[Tuple[str, ...], str, object]]
IndexSnapshot = List[Tuple[str, Tuple[str, ...], bool]]


class TestMigrations:
    """Tests that the migrations and the ORM metadata describe one schema."""

    def _snapshot(self, engine: Engine) -> Dict[str, object]:
        """Describe every table an engine holds.

        Args:
            engine (Engine): The engine to inspect.

        Returns:
            Dict[str, object]: Per table, its columns, foreign keys and
            indexes, in a form that compares by value.

        Notes:
            Alembic's own bookkeeping table is skipped: it exists only in the
            migrated database and is not part of the application schema.
        """
        inspector = inspect(engine)
        snapshot: Dict[str, object] = {}
        for table in sorted(inspector.get_table_names()):
            if table == "alembic_version":
                continue
            columns: ColumnSnapshot = {
                column["name"]: (str(column["type"]).upper(), bool(column["nullable"]))
                for column in inspector.get_columns(table)
            }
            foreign_keys: ForeignKeySnapshot = sorted(
                (
                    tuple(key["constrained_columns"]),
                    key["referred_table"],
                    (key.get("options") or {}).get("ondelete"),
                )
                for key in inspector.get_foreign_keys(table)
            )
            indexes: IndexSnapshot = sorted(
                (index["name"], tuple(index["column_names"]), bool(index["unique"]))
                for index in inspector.get_indexes(table)
            )
            snapshot[table] = {
                "columns": columns,
                "foreign_keys": foreign_keys,
                "indexes": indexes,
            }
        return snapshot

    def _migrated_engine(self, database_path: Path) -> Engine:
        """Build an engine whose schema comes from running the migrations.

        Args:
            database_path (Path): Where to create the scratch database.

        Returns:
            Engine: An engine pointing at the migrated database.

        Notes:
            The revision's ``upgrade`` is driven directly rather than through
            ``command.upgrade`` so this test does not need the application
            configuration, a PostgreSQL URL or a database password.
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
                # walk_revisions yields newest-first; migrations must be applied
                # oldest-first or a table is created before the one its foreign
                # key points at.
                revisions = list(script.walk_revisions(base="base", head="heads"))
                for revision in reversed(revisions):
                    revision.module.upgrade()
        return engine

    def test_the_migration_matches_the_orm_metadata(self, tmp_path: Path) -> None:
        """Running the migrations yields the schema the ORM describes.

        Notes:
            This is the test that catches the classic drift: a column added to
            an ORM row without a matching migration. The repository suite would
            still pass — it creates its schema from the metadata — and only
            production, which is migrated, would break.
        """
        migrated = self._migrated_engine(tmp_path / "migrated.db")
        from_metadata = create_engine(f"sqlite:///{tmp_path / 'metadata.db'}")
        Base.metadata.create_all(from_metadata)
        assert self._snapshot(migrated) == self._snapshot(from_metadata)

    def test_the_migration_creates_every_table(self, tmp_path: Path) -> None:
        """Every table the ORM declares exists after migrating."""
        migrated = self._migrated_engine(tmp_path / "migrated.db")
        assert set(self._snapshot(migrated)) == set(Base.metadata.tables)

    def test_the_account_email_index_is_unique(self, tmp_path: Path) -> None:
        """Two accounts cannot share a sign-in address, at the schema level."""
        migrated = self._migrated_engine(tmp_path / "migrated.db")
        indexes = inspect(migrated).get_indexes("users")
        email_index = next(
            index for index in indexes if index["column_names"] == ["email"]
        )
        # The inspector reports the flag as 1 rather than True on SQLite.
        assert bool(email_index["unique"]) is True

    def test_deleting_an_assistant_is_restricted_by_the_account_link(
        self, tmp_path: Path
    ) -> None:
        """The account foreign key restricts rather than cascades.

        Notes:
            Cascading here would delete a person's account because their
            assistant record was removed; restricting forces the operator to
            deal with the account first.
        """
        migrated = self._migrated_engine(tmp_path / "migrated.db")
        keys = inspect(migrated).get_foreign_keys("users")
        hca_key = next(key for key in keys if key["referred_table"] == "hcas")
        assert (hca_key.get("options") or {}).get("ondelete") == "RESTRICT"

    @pytest.mark.parametrize("table", ["certifications", "availability_slots"])
    def test_assistant_children_cascade(self, tmp_path: Path, table: str) -> None:
        """Qualifications and absences are deleted with their assistant."""
        migrated = self._migrated_engine(tmp_path / "migrated.db")
        keys = inspect(migrated).get_foreign_keys(table)
        hca_key = next(key for key in keys if key["referred_table"] == "hcas")
        assert (hca_key.get("options") or {}).get("ondelete") == "CASCADE"
