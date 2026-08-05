from __future__ import annotations

# Standard library imports
import asyncio
import logging
from logging import Logger, getLogger
from logging.config import dictConfig
import os
from pathlib import Path
import signal
from typing import Optional

from worker.handlers import EventHandlers

# Third-party imports
import yaml

# First-party imports
from models.configuration.app_config import AppConfig
from models.enums import EventRoutingKey
from service.messaging.consumer import EventConsumer

logger: Logger = getLogger(__name__)

# One queue per kind of work, rather than one queue for everything. The planning
# solve pins a core for thirty seconds; sharing a queue with the notification
# fan-out would leave a manager waiting half a minute to be told a quote needs
# looking at, behind work that has nothing to do with them.
PLANNING_QUEUE: str = "planning-runs"
NOTIFICATION_QUEUE: str = "quote-notifications"


async def run() -> None:
    """Consume both queues until the process is asked to stop.

    Notes:
        The two consumers share a process but not a queue, so the broker can
        deliver a notification while a solve is in flight. Running them as two
        processes would be tidier still, and is what the compose file does in
        production by scaling this one — the queues are already separate, so
        that needs no code change.
    """
    config = AppConfig.load()
    handlers = EventHandlers(config=config, logger=logger)

    planning = EventConsumer(config=config.rabbitmq, logger=logger)
    planning.on(EventRoutingKey.PLANNING_RUN_REQUESTED, handlers.run_planning)

    notifications = EventConsumer(config=config.rabbitmq, logger=logger)
    notifications.on(EventRoutingKey.QUOTE_SUBMITTED, handlers.quote_submitted)
    notifications.on(EventRoutingKey.QUOTE_VALIDATED, handlers.quote_validated)
    notifications.on(EventRoutingKey.QUOTE_REFUSED, handlers.quote_refused)
    notifications.on(
        EventRoutingKey.PLANNING_RUN_COMPLETED, handlers.planning_completed
    )

    await planning.run(PLANNING_QUEUE, [EventRoutingKey.PLANNING_RUN_REQUESTED])
    await notifications.run(
        NOTIFICATION_QUEUE,
        [
            EventRoutingKey.QUOTE_SUBMITTED,
            EventRoutingKey.QUOTE_VALIDATED,
            EventRoutingKey.QUOTE_REFUSED,
            EventRoutingKey.PLANNING_RUN_COMPLETED,
        ],
    )
    logger.info("Worker is consuming; waiting for messages.")

    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for received in (signal.SIGINT, signal.SIGTERM):
        # Handled rather than left to the default, so an in-flight solve is
        # allowed to finish and acknowledge instead of being killed mid-message
        # and redelivered from the start.
        loop.add_signal_handler(received, stopping.set)
    await stopping.wait()

    logger.info("Worker is shutting down.")
    await planning.close()
    await notifications.close()
    await handlers.close()


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
    getLogger(__name__).info("Starting the rt-erp worker.")
    asyncio.run(run())


if __name__ == "__main__":
    main()
