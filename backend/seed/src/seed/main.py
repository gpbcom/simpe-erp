from __future__ import annotations

# Standard library imports
import asyncio
import logging
from logging import getLogger
from typing import List, Optional

from seed.dataset import Dataset
from seed.seeder import Seeder

# First-party imports
from models.configuration.app_config import AppConfig
from service.auth.auth import AuthService
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
    data = Dataset()
    try:
        async with manager.session() as session:
            # The hasher is borrowed from the real authentication service, so a
            # seeded password is hashed exactly as a registered one is. A
            # seeder with its own hashing is a seeder whose accounts cannot
            # sign in the day the cost factor changes.
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

            author_ids = await _assistant_account_ids(session, data, assistants)
            await seeder.seed_quotes(customers, catalog, author_ids)
    finally:
        await manager.disconnect()

    _print_credentials(data)


async def _assistant_account_ids(session, data: Dataset, assistants: List) -> List[str]:
    """Return the account identifiers behind the seeded assistants.

    Args:
        session: The open database session.
        data (Dataset): The fixed contents, for the identifier derivation.
        assistants (List): The seeded assistants.

    Returns:
        List[str]: The account identifiers, so quotes can be attributed to
        real signed-in accounts rather than to nobody.

    Notes:
        A quote's ``authored_by`` is an **account**, not an assistant. Seeding
        it with the assistant's identifier would put every quote outside every
        assistant's own list, because that list filters on the account.
    """
    return [data.identifier("user", str(assistant.email)) for assistant in assistants]


def _print_credentials(data: Dataset) -> None:
    """Print the seeded sign-ins.

    Args:
        data (Dataset): The fixed contents, for the shared password.

    Notes:
        Printed rather than logged at ``INFO``, and printed every run rather
        than only when something was written. A developer who reruns the stack
        a week later needs the password on screen, not in a log file from the
        first run.
    """
    print()
    print("  rt-erp is seeded. Sign in at http://localhost:5173 with:")
    print()
    print(f"    Administrator   admin@rt-erp.fr      {data.PASSWORD}")
    print(f"    Manager         manager@rt-erp.fr    {data.PASSWORD}")
    print(f"    Assistant       luc.martin@rt-erp.fr {data.PASSWORD}")
    print()
    print("  Every seeded assistant signs in with firstname.lastname@rt-erp.fr.")
    print()


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
