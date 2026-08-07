from __future__ import annotations

# Standard library imports
import asyncio
import logging

import os  # isort: skip
import sys
from logging import Logger, getLogger
from logging.config import dictConfig
from pathlib import Path
from typing import Final, List, Optional

# Third-party imports
import yaml

# First-party imports
from models.configuration.app_config import AppConfig
from models.enums import WorkerRole

from worker.runner import WorkerRunner  # isort: skip

logger: Logger = getLogger(__name__)

LOGGER_PATH_ENV: Final[str] = "SIMPLE_ERP_LOGGER"
DEFAULT_LOGGER_PATH: Final[str] = "conf/logger.yaml"


async def run(role: WorkerRole) -> None:
    """Run the worker until it is asked to stop.

    Args:
        role (WorkerRole): What this process consumes.

    Notes:
        The work lives in :class:`~worker.runner.WorkerRunner`. This module
        stays an entry point: read the configuration, configure logging, hand
        over.
    """
    await WorkerRunner(config=AppConfig.load(), role=role, logger=logger).run()


def resolve_role(argv: Optional[List[str]] = None) -> WorkerRole:
    """Read which role this process was started as.

    Args:
        argv (Optional[List[str]]): Arguments, without the program name.
            Defaults to :data:`sys.argv`.

    Returns:
        WorkerRole: The role named on the command line.

    Raises:
        SystemExit: If no role was given, or the one given is not a role.

    Notes:
        - **Required, with no default.** The two roles want different replica
          counts, different resources and different node pools, so a process that
          guessed would be one somebody had to notice was doing the wrong job —
          and the way they would notice is a queue that never drains.
        - Exiting rather than raising: this is the first thing the container does,
          and a usage message on stderr with a non-zero status is what a crash-loop
          should show somebody reading ``kubectl logs``.
    """
    arguments = argv if argv is not None else sys.argv[1:]
    if not arguments:
        raise SystemExit(
            f"Usage: worker <{'|'.join(WorkerRole.values())}>. "
            f"The role decides which queue this process consumes."
        )
    try:
        return WorkerRole(arguments[0])
    except ValueError:
        raise SystemExit(
            f"Unknown worker role {arguments[0]!r}. "
            f"Must be one of: {', '.join(WorkerRole.values())}."
        ) from None


def setup_logging(config_path: Optional[str] = None) -> None:
    """Configure logging from the same YAML file the API uses.

    Args:
        config_path (Optional[str]): Path to the logging configuration.
            Defaults to what ``SIMPLE_ERP_LOGGER`` names, and to the
            development configuration when that is unset.

    Notes:
        Duplicated from the API rather than imported from it. The worker
        depends on ``models``, ``storage`` and ``service`` and deliberately not
        on ``api`` — a background consumer that pulled in FastAPI, uvicorn and
        the whole HTTP layer to read one YAML file would make the dependency
        graph a ring. Fifteen lines is the cheaper price.
    """
    chosen = config_path if config_path else os.environ.get(
        LOGGER_PATH_ENV, DEFAULT_LOGGER_PATH
    )
    resolved = Path(chosen)
    if not resolved.exists():
        # main.py -> worker -> src -> worker -> backend
        resolved = Path(__file__).resolve().parents[3] / chosen
    try:
        with open(resolved, "r", encoding="utf-8") as config_file:
            configuration = yaml.safe_load(config_file)
        os.makedirs("logs", exist_ok=True)
        dictConfig(configuration)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        logging.basicConfig(level=logging.INFO)
        getLogger(__name__).error(
            "Falling back to basic logging; could not read %s: %s.", resolved, exc
        )


def main(argv: Optional[List[str]] = None) -> None:
    """Run the worker in the role it was started as.

    Args:
        argv (Optional[List[str]]): Arguments, without the program name.
            Defaults to :data:`sys.argv`.

    Notes:
        One image, two deployments: ``worker planning`` solves and
        ``worker notifications`` writes notifications and sends email. They are
        split because a solve pins its cores for thirty seconds while a
        notification finishes in milliseconds, so sharing a process means the
        two scale together and a manager waits half a minute for a badge.
    """
    role = resolve_role(argv)
    setup_logging()
    getLogger(__name__).info("Starting the simple-erp %s worker.", role.value)
    asyncio.run(run(role))


if __name__ == "__main__":
    main()
