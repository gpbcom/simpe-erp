from __future__ import annotations

# Standard library imports
from pathlib import Path
from typing import Iterator, List, Tuple

# Third-party imports
import pytest
from sqlalchemy import Engine, text

# First-party imports
from migration_templates import MigrationTemplates

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def migrated_to_0013(
    tmp_path: Path, migrations: MigrationTemplates
) -> Iterator[Engine]:
    """Return a database at revision 0013, before the name split.

    Args:
        tmp_path (Path): A directory for this test's own database.
        migrations (MigrationTemplates): The per-worker template cache.

    Yields:
        Engine: An engine pointing at this test's own copy.

    Notes:
        Stopped one revision short on purpose. The point of this suite is what
        0014 does to rows that already exist, and a database migrated all the
        way has none.

        The chain is replayed **once per worker**, not once per test: the cache
        builds a template at 0013 and this copies it. Each test still owns its
        own file and may migrate it freely.
    """
    engine = migrations.copy_to(tmp_path / "backfill.sqlite", stop_after="0013")
    yield engine
    engine.dispose()


def _seed(engine: Engine, display_names: List[str]) -> None:
    """Insert one account per display name, as revision 0013 stored them.

    Args:
        engine (Engine): The database to write to.
        display_names (List[str]): The names to store.
    """
    with engine.begin() as connection:
        for index, display_name in enumerate(display_names):
            connection.execute(
                text(
                    "INSERT INTO users (id, email, full_name, role, is_active, "
                    "company_id, account_origin, must_change_password, "
                    "created_at, updated_at) VALUES (:id, :email, :full_name, "
                    "'manager', 1, 'company-1', 'self-registered', 0, "
                    "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                ),
                {
                    "id": f"user-{index}",
                    "email": f"user-{index}@example.com",
                    "full_name": display_name,
                },
            )


def _names(engine: Engine) -> List[Tuple[str, str]]:
    """Return every account's two names, in insertion order.

    Args:
        engine (Engine): The database to read.

    Returns:
        List[Tuple[str, str]]: The given and family names.
    """
    with engine.connect() as connection:
        return [
            (row[0], row[1])
            for row in connection.execute(
                text("SELECT first_name, last_name FROM users ORDER BY id")
            ).all()
        ]


class TestMigration0014Backfill:
    """Tests that splitting the display name loses nothing."""

    def test_an_ordinary_name_splits_into_two(
        self, migrated_to_0013: Engine, migrations: MigrationTemplates
    ) -> None:
        """The common case: a given name and a family name.

        Args:
            migrated_to_0013 (Engine): The database at revision 0013.
            migrations (MigrationTemplates): The template cache.
        """
        engine = migrated_to_0013
        _seed(engine, ["Claire Bernard"])

        migrations.apply(engine, "0014")

        assert _names(engine) == [("Claire", "Bernard")]

    def test_a_long_family_name_stays_whole(
        self, migrated_to_0013: Engine, migrations: MigrationTemplates
    ) -> None:
        """**Split on the first space, not the last.**

        Args:
            migrated_to_0013 (Engine): The database at revision 0013.
            migrations (MigrationTemplates): The template cache.

        Notes:
            Splitting on the last space reads back identically but files the
            person under "Tour" instead of "Pierre de la Tour" — a wrong
            surname that no screen would ever show and nothing would catch.
        """
        engine = migrated_to_0013
        _seed(engine, ["Jean Pierre de la Tour"])

        migrations.apply(engine, "0014")

        assert _names(engine) == [("Jean", "Pierre de la Tour")]

    def test_a_mononym_becomes_a_family_name(
        self, migrated_to_0013: Engine, migrations: MigrationTemplates
    ) -> None:
        """A one-word name is not a given name with a missing surname.

        Args:
            migrated_to_0013 (Engine): The database at revision 0013.
            migrations (MigrationTemplates): The template cache.

        Notes:
            An account called ``root`` is real, and inventing a given name for
            it would be worse than leaving the column blank. The model permits
            an empty given name on an account for exactly this row.
        """
        engine = migrated_to_0013
        _seed(engine, ["Root"])

        migrations.apply(engine, "0014")

        assert _names(engine) == [("", "Root")]

    def test_every_existing_account_is_backfilled(
        self, migrated_to_0013: Engine, migrations: MigrationTemplates
    ) -> None:
        """No row is left with two empty names.

        Args:
            migrated_to_0013 (Engine): The database at revision 0013.
            migrations (MigrationTemplates): The template cache.

        Notes:
            The columns land with a server-side default of ``''`` so the
            constraint can be added before the backfill runs. A row the backfill
            missed would therefore be silently nameless rather than a failure.
        """
        engine = migrated_to_0013
        _seed(engine, ["Claire Bernard", "Root", "Ana Lopez", "  Luc  Martin  "])

        migrations.apply(engine, "0014")

        assert all(family for _, family in _names(engine))

    def test_the_downgrade_restores_the_display_name(
        self, migrated_to_0013: Engine, migrations: MigrationTemplates
    ) -> None:
        """Going back recomposes exactly what was there.

        Args:
            migrated_to_0013 (Engine): The database at revision 0013.
            migrations (MigrationTemplates): The template cache.
        """
        engine = migrated_to_0013
        _seed(engine, ["Claire Bernard", "Root", "Jean Pierre de la Tour"])

        migrations.apply(engine, "0014")
        migrations.apply(engine, "0014", downgrade=True)

        with engine.connect() as connection:
            restored = [
                row[0]
                for row in connection.execute(
                    text("SELECT full_name FROM users ORDER BY id")
                ).all()
            ]
        assert restored == ["Claire Bernard", "Root", "Jean Pierre de la Tour"]
