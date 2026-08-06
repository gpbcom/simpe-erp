from __future__ import annotations

# Standard library imports
import asyncio
import logging
from logging import Logger, getLogger
from logging.config import dictConfig
import os
from pathlib import Path
from typing import Optional

from worker.runner import WorkerRunner

# Third-party imports
import yaml

# First-party imports
from models.configuration.app_config import AppConfig

logger: Logger = getLogger(__name__)



async def run() -> None:
    """Run the worker until it is asked to stop.

    Notes:
        The work lives in :class:`~worker.runner.WorkerRunner`. This module
        stays an entry point: read the configuration, configure logging, hand
        over.
    """
    await WorkerRunner(config=AppConfig.load(), logger=logger).run()


def setup_logging(config_path: str = "conf/logger.yaml") -> None:
    """Configure logging from the same YAML file the API uses.

    Args:
        config_path (str): Path to the logging configuration.

    Notes:
        Duplicated from the API rather than imported from it. The worker
        depends on ``models``, ``storage`` and ``service`` and deliberately not
        on ``api`` — a background consumer that pulled in FastAPI, uvicorn and
        the whole HTTP layer to read one YAML file would make the dependency
        graph a ring. Fifteen lines is the cheaper price.
    """
    resolved = Path(config_path)
    if not resolved.exists():
        # main.py -> worker -> src -> worker -> backend
        resolved = Path(__file__).resolve().parents[3] / config_path
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


def main(argv: Optional[list] = None) -> None:
    """Run the worker.

    Args:
        argv (Optional[list]): Unused; present so the console script matches
            the shape of the API's entry point.
    """
    setup_logging()
    getLogger(__name__).info("Starting the simple-erp worker.")
    asyncio.run(run())


if __name__ == "__main__":
    main()
