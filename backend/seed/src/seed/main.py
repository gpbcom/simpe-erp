from __future__ import annotations

# Standard library imports
import asyncio
import logging
from logging import getLogger
from typing import Optional

# First-party imports
from models.configuration.app_config import AppConfig
from models.enums import EventRoutingKey
from service.auth.auth import AuthService
from service.messaging.publisher import EventPublisher

from seed.seeder import Seeder  # isort: skip
from storage.db.connection_manager import DatabaseConnectionManager
from storage.repositories.hca import HcaRepository
from storage.repositories.user import UserRepository

logger = getLogger(__name__)


async def _announce(company_id: str, config: AppConfig) -> None:
    """Tell the worker about the agency this run seeded.

    Args:
        company_id (str): The agency that was seeded.
        config (AppConfig): The application configuration, for the broker.

    Notes:
        - **Without this the dev stack silently drops every event it produces.**
          The worker's queues are per agency: it enumerates the companies it
          finds at start-up and binds one queue each, and thereafter learns about
          new ones from ``company.created``. Compose starts the worker and this
          container together, so the worker enumerates an empty database, finds
          nothing, and binds nothing — then the seeder writes the agency straight
          into the database and says nothing. Every quote submitted afterwards is
          published to a routing key with no queue behind it, so no notification
          is ever delivered and no planning run is ever solved, and none of it
          logs an error anywhere.
        - Announcing closes that gap the same way self-registration already does.
          Serving an agency is idempotent, so a re-seed against a worker that is
          already bound costs one ignored message.
        - A broker that cannot be reached is **logged and passed over**. Seeding a
          database must not require a broker; a developer who has started only
          PostgreSQL still gets their data, and the worker will enumerate the
          agency for itself the next time it starts.
    """
    publisher = EventPublisher(config=config.rabbitmq, logger=logger)
    try:
        announced = await publisher.publish(
            EventRoutingKey.COMPANY_CREATED, company_id, {"company_id": company_id}
        )
        if announced:
            logger.info("Announced agency %s to the worker.", company_id)
        else:
            logger.warning(
                "Could not announce agency %s: the worker will pick it up when "
                "it next starts.",
                company_id,
            )
    finally:
        await publisher.close()


async def run() -> None:
    """Seed the database, then print how to sign in.

    Notes:
        One session for the whole run, so the seed is one transaction: a
        failure half-way leaves an empty database rather than an agency with
        customers but no accounts, which is harder to recognise as broken than
        nothing at all.
    """
    config = AppConfig.load()
    manager = DatabaseConnectionManager(config=config.database, logger=logger)
    seeder: Optional[Seeder] = None
    try:
        await manager.connect()
        async with manager.session() as session:
            auth = AuthService(
                users=UserRepository(session=session, logger=logger),
                hcas=HcaRepository(session=session, logger=logger),
                config=config.auth,
                logger=logger,
            )
            seeder = Seeder(
                session=session,
                hasher=auth,
                pricing=config.pricing,
                logger=logger,
            )

            company_id = await seeder.seed_company()
            catalog = await seeder.seed_catalog()
            assistants = await seeder.seed_assistants(company_id)
            customers = await seeder.seed_customers()
            await seeder.seed_accounts(company_id, assistants)

            author_ids = seeder.account_ids_for(assistants)
            await seeder.seed_quotes(customers, catalog, author_ids)
        await _announce(company_id, config)
    finally:
        await manager.disconnect()

    if seeder is not None:
        seeder.print_credentials()


def main(argv: Optional[list] = None) -> None:
    """Run the seeder.

    Args:
        argv (Optional[list]): Unused; present so the console script matches
            the shape of the other entry points.
    """
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-8s %(name)s: %(message)s"
    )
    logger.info("Seeding the SimpleERP database.")
    asyncio.run(run())


if __name__ == "__main__":
    main()
