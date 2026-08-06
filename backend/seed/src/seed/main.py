from __future__ import annotations

# Standard library imports
import asyncio
import logging
from logging import getLogger
from typing import Optional

# First-party imports
from models.configuration.app_config import AppConfig
from service.auth.auth import AuthService
from seed.seeder import Seeder  # isort: skip
from storage.db.connection_manager import DatabaseConnectionManager
from storage.repositories.hca import HcaRepository
from storage.repositories.user import UserRepository

logger = getLogger(__name__)


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
        # Opened explicitly. `session()` asks the manager for its factory and
        # refuses when there is none, so without this the seeder dies on
        # `MTDatabaseNotConnected` before writing a row. `connect()` also
        # retries, which matters here more than it does in the API: compose
        # starts this container as soon as PostgreSQL reports healthy, and
        # healthy is a moment or two before it is accepting connections.
        await manager.connect()
        async with manager.session() as session:
            auth = AuthService(
                users=UserRepository(session=session, logger=logger),
                hcas=HcaRepository(session=session, logger=logger),
                config=config.auth,
                logger=logger,
            )
            seeder = Seeder(session=session, hasher=auth, logger=logger)

            company_id = await seeder.seed_company()
            catalog = await seeder.seed_catalog()
            assistants = await seeder.seed_assistants(company_id)
            customers = await seeder.seed_customers()
            await seeder.seed_accounts(company_id, assistants)

            author_ids = seeder.account_ids_for(assistants)
            await seeder.seed_quotes(customers, catalog, author_ids)
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
    logger.info("Seeding the rt-erp database.")
    asyncio.run(run())


if __name__ == "__main__":
    main()
