from __future__ import annotations

# Standard library imports
import logging
from logging import Logger, getLogger
from pathlib import Path
from typing import Final

# Third-party imports
from alembic import command
from alembic.config import Config

logger: Logger = getLogger(__name__)

CONFIG_PATH: Final[str] = "conf/alembic.ini"


def resolve_config(config_path: str = CONFIG_PATH) -> Path:
    """Locate ``alembic.ini`` from wherever this was invoked.

    Args:
        config_path (str): Path to the Alembic configuration.

    Returns:
        Path: The resolved path.

    Notes:
        Relative to the working directory first, then to the backend project
        root — the same two-step resolution
        :meth:`~models.configuration.app_config.AppConfig.load` performs, and
        for the same reason: the container runs from ``/app`` while a developer
        runs from anywhere.
    """
    resolved = Path(config_path)
    if resolved.exists():
        return resolved
    # migrate.py -> storage -> src -> storage -> backend
    return Path(__file__).resolve().parents[3] / config_path


def upgrade(revision: str = "head", config_path: str = CONFIG_PATH) -> None:
    """Bring the database up to a revision.

    Args:
        revision (str): The revision to migrate to. Defaults to ``head``.
        config_path (str): Path to the Alembic configuration.

    Raises:
        Exception: Whatever Alembic raises. A migration that cannot be applied
            must stop the deployment, so nothing is swallowed here.
    """
    resolved = resolve_config(config_path)
    logger.info("Migrating to %s using %s.", revision, resolved)
    if not resolved.exists():
        logger.error("No Alembic configuration at %s.", resolved)
        raise FileNotFoundError(f"No Alembic configuration at {resolved}.")
    try:
        command.upgrade(Config(str(resolved)), revision)
    except Exception as exc:
        logger.error("Migration to %s failed: %s.", revision, exc)
        raise
    logger.info("The database is at %s.", revision)


def main() -> None:
    """Run the migrations to ``head`` and exit.

    Notes:
        - No arguments, and none to add. A deployment migrates forwards to
          ``head`` — that is what the compose service and the Helm hook both mean
          — and a targeted revision is a recovery action somebody performs
          deliberately with ``alembic`` in hand, not something an unattended Job
          should be able to be handed. :func:`upgrade` takes the revision for the
          cases that genuinely need one.
        - **This exists so that migrating is a process, not a prefix.** It used to
          be the first half of the API container's start command
          (``alembic upgrade head && uvicorn …``), which meant every API replica
          ran it — fine with one, a race with two, and "how a deployment ends up
          half-upgraded" by the architecture's own account.
        - As an entry point it can be a one-shot compose service the API depends
          on and a Helm ``pre-upgrade`` hook Job, which are the same arrangement
          described twice rather than two arrangements that have to agree.
        - Logging is configured here rather than inherited: this runs before the
          API exists, and a migration that failed silently in a Job that then
          exited non-zero is a deployment nobody can explain.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    upgrade()
