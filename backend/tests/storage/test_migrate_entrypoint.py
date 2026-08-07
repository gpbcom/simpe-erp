from __future__ import annotations

# Standard library imports
from pathlib import Path
from unittest.mock import patch

# Third-party imports
import pytest

# First-party imports
from storage.migrate import CONFIG_PATH, main, resolve_config, upgrade


class TestMigrateEntrypoint:
    """Tests for the process that brings the database up to date.

    Notes:
        **Why this is a process at all.** Migrating used to be the first half of
        the API container's start command — ``alembic upgrade head && uvicorn``
        — so every API replica ran it. That is fine with one replica, a race
        with two, and "how a deployment ends up half-upgraded" by the
        architecture's own account.

        As an entry point it becomes a one-shot compose service the API depends
        on and a Helm ``pre-upgrade`` hook Job: the same arrangement described
        twice, rather than two arrangements that have to agree.
    """

    # ------------------------------------------------------------------ #
    #  Finding the configuration
    # ------------------------------------------------------------------ #

    def test_the_configuration_is_found_from_the_backend_root(self) -> None:
        """The real ``alembic.ini`` resolves, wherever the tests were started.

        Notes:
            The container runs from ``/app`` and a developer runs from
            anywhere, so a path that only worked from one of them would fail in
            exactly the place nobody tests.
        """
        assert resolve_config().exists()

    def test_a_configuration_beside_the_caller_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A local file is preferred over the packaged one.

        Args:
            tmp_path (Path): Scratch directory.
            monkeypatch (pytest.MonkeyPatch): Used to move the working
                directory.
        """
        (tmp_path / "conf").mkdir()
        (tmp_path / CONFIG_PATH).write_text("[alembic]\n")
        monkeypatch.chdir(tmp_path)

        assert resolve_config() == Path(CONFIG_PATH)

    # ------------------------------------------------------------------ #
    #  Running
    # ------------------------------------------------------------------ #

    def test_it_migrates_to_head_by_default(self) -> None:
        """``head`` is what a deployment means by "migrate"."""
        with patch("storage.migrate.command") as alembic:
            upgrade()

        assert alembic.upgrade.call_args.args[1] == "head"

    def test_a_revision_can_be_named(self) -> None:
        """Pinning one is how a recovery is driven."""
        with patch("storage.migrate.command") as alembic:
            upgrade("0015")

        assert alembic.upgrade.call_args.args[1] == "0015"

    def test_the_entry_point_takes_no_arguments(self) -> None:
        """**An unattended Job can only ever move forwards.**

        Notes:
            A targeted revision is a recovery action somebody performs
            deliberately with ``alembic`` in hand. Exposing it on the command a
            Helm hook runs would make "roll the schema back" something a values
            file could ask for by accident.
        """
        with patch("storage.migrate.command") as alembic:
            main()

        assert alembic.upgrade.call_args.args[1] == "head"

    # ------------------------------------------------------------------ #
    #  Failing loudly
    # ------------------------------------------------------------------ #

    def test_a_missing_configuration_raises(self) -> None:
        """A configuration that is not there stops the deployment.

        Notes:
            Both resolution steps have to miss for this, which in practice means
            the image was built without ``conf/``. Exiting non-zero is what
            makes the Job fail and the rollout stop, rather than an API coming
            up against a schema nothing upgraded.
        """
        with pytest.raises(FileNotFoundError):
            upgrade(config_path="nowhere/alembic.ini")

    def test_a_failed_migration_is_not_swallowed(self) -> None:
        """Alembic's own failure travels out untouched.

        Notes:
            **Nothing is caught and turned into a warning here.** A migration
            that could not be applied and a deployment that carried on is the
            pairing this entry point exists to prevent; the log line names the
            revision, and then the exception ends the process.
        """
        with patch("storage.migrate.command") as alembic:
            alembic.upgrade.side_effect = RuntimeError("relation does not exist")

            with pytest.raises(RuntimeError, match="relation does not exist"):
                upgrade()
