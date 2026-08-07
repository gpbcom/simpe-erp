from __future__ import annotations

# Standard library imports
from pathlib import Path
from shutil import copyfile
from typing import Dict, List, Optional

# Third-party imports
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.script.base import Script
from sqlalchemy import Engine, create_engine

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class MigrationTemplates:
    """Replays the Alembic chain once per revision, then hands out copies.

    Attributes:
        root (Path): Directory the template databases are built in.
        templates (Dict[str, Path]): Built template file, per stop revision.

    Notes:
        - **Why this exists.** Replaying the chain costs about a second, and the
          four migration suites were each paying it *per test* — twenty-odd
          replays for twenty-two tests, measured at **19 s of a 52 s serial
          run**, the single largest cost in the backend suite. The chain is
          deterministic and its result is a small SQLite file, so it is built
          once per stop revision and copied thereafter. A copy is about a
          millisecond.
        - **Each test still gets its own database.** The template is never
          opened by a test; it is copied first. Isolation is unchanged — what
          is shared is the *work of building*, not the file.
        - Session-scoped, and therefore **per xdist worker**. A worker builds
          only the revisions its own tests ask for, so the parallel run pays for
          at most what it uses rather than for the whole matrix.
        - The ``ScriptDirectory`` is parsed once too. Reading fourteen revision
          modules off disk is not free either, and every suite was doing it in
          every helper call.
    """

    def __init__(self, root: Path) -> None:
        """Initialize the cache.

        Args:
            root (Path): Directory to build the template databases in.
        """
        self.root = root
        self.templates: Dict[str, Path] = {}
        self._script: Optional[ScriptDirectory] = None

    ############################
    # Internal Helpers Methods #
    ############################

    def _scripts(self) -> ScriptDirectory:
        """Return the Alembic script directory, parsed once.

        Returns:
            ScriptDirectory: The revision scripts.

        Notes:
            Built from a bare :class:`Config` with only ``script_location`` set,
            so this needs no application configuration, no PostgreSQL URL and no
            password — the approach every migration suite already took.
        """
        if self._script is None:
            config = Config()
            config.set_main_option(
                "script_location", str(BACKEND_ROOT / "conf" / "alembic")
            )
            self._script = ScriptDirectory.from_config(config)
        return self._script

    def _build(self, stop_after: Optional[str]) -> Path:
        """Build one template database and return its path.

        Args:
            stop_after (Optional[str]): The last revision to apply, or ``None``
                to migrate to head.

        Returns:
            Path: The template file.
        """
        template = self.root / f"template-{stop_after or 'head'}.sqlite"
        engine = create_engine(f"sqlite:///{template}")
        try:
            with engine.begin() as connection:
                context = MigrationContext.configure(connection)
                with Operations.context(context):
                    for revision in self.revisions():
                        revision.module.upgrade()
                        if revision.revision == stop_after:
                            break
        finally:
            engine.dispose()
        return template

    ############################
    # Publicly Exposed Methods #
    ############################

    def revisions(self) -> List[Script]:
        """Return every revision, oldest first.

        Returns:
            List[Script]: The revision scripts in application order.

        Notes:
            ``walk_revisions`` yields newest-first; migrations must be applied
            in the opposite order, which is why this reverses.
        """
        return list(
            reversed(list(self._scripts().walk_revisions(base="base", head="heads")))
        )

    def revision(self, revision_id: str) -> Script:
        """Return one revision by identifier.

        Args:
            revision_id (str): The revision to find.

        Returns:
            Script: The revision script.
        """
        return next(
            entry for entry in self.revisions() if entry.revision == revision_id
        )

    def copy_to(self, destination: Path, stop_after: Optional[str] = None) -> Engine:
        """Copy a template database to a path and return an engine on it.

        Args:
            destination (Path): Where the test's own database should live.
            stop_after (Optional[str]): The last revision the copy should carry,
                or ``None`` for head.

        Returns:
            Engine: An engine pointing at the test's own copy.

        Notes:
            The template is built on first request for a given stop revision and
            reused afterwards. The caller owns the copy and may migrate, write
            to or corrupt it freely.
        """
        key = stop_after or "head"
        if key not in self.templates:
            self.templates[key] = self._build(stop_after)
        copyfile(self.templates[key], destination)
        return create_engine(f"sqlite:///{destination}")

    def apply(self, engine: Engine, revision_id: str, downgrade: bool = False) -> None:
        """Run one revision against an already-migrated database.

        Args:
            engine (Engine): The database to migrate.
            revision_id (str): The revision to run.
            downgrade (bool): Whether to run its downgrade instead.
        """
        revision = self.revision(revision_id)
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                if downgrade:
                    revision.module.downgrade()
                else:
                    revision.module.upgrade()
