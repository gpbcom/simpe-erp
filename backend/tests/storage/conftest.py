from __future__ import annotations

# Standard library imports
from typing import Any, AsyncIterator, Dict

# Third-party imports
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# First-party imports
from models.enums import ContractType
from models.people.customer import Customer
from models.people.hca import Hca
from storage.orm import Base


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Yield a session bound to a fresh in-memory SQLite database.

    Yields:
        AsyncSession: A session with the full schema created and foreign keys
        enforced.

    Notes:
        SQLite rather than PostgreSQL keeps the repository suite hermetic and
        fast — no container, no port, nothing to clean up between runs. The ORM
        stays portable for exactly this reason: ``JSON`` carries a PostgreSQL
        variant, and no PostgreSQL-only column type is used.

        ``PRAGMA foreign_keys=ON`` is essential. SQLite ignores foreign keys by
        default, so without it the tests asserting that a restricted delete is
        refused would pass for the wrong reason — the delete would simply
        succeed and leave a dangling row.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as connection:
        from sqlalchemy import text

        await connection.execute(text("PRAGMA foreign_keys=ON"))
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as open_session:
        from sqlalchemy import text

        await open_session.execute(text("PRAGMA foreign_keys=ON"))
        yield open_session

    await engine.dispose()


@pytest.fixture
def customer_kwargs() -> Dict[str, Any]:
    """Return the keyword arguments for a valid customer.

    Returns:
        Dict[str, Any]: Constructor keyword arguments.
    """
    return {
        "first_name": "Marie",
        "last_name": "Durand",
        "phone_number": "+33612345678",
        "email": "marie.durand@example.com",
        "address": {
            "street": "12 rue de Rivoli",
            "postal_code": "75004",
            "city": "Paris",
            "latitude": 48.8566,
            "longitude": 2.3522,
        },
    }


@pytest.fixture
def customer(customer_kwargs: Dict[str, Any]) -> Customer:
    """Return an unsaved customer.

    Args:
        customer_kwargs (Dict[str, Any]): Constructor keyword arguments.

    Returns:
        Customer: A customer with no identifier yet.
    """
    return Customer(**customer_kwargs)


@pytest.fixture
def hca_kwargs() -> Dict[str, Any]:
    """Return the keyword arguments for a valid assistant.

    Returns:
        Dict[str, Any]: Constructor keyword arguments.
    """
    return {
        "first_name": "Luc",
        "last_name": "Martin",
        "phone_number": "+33698765432",
        "email": "luc.martin@example.com",
        "address": {
            "street": "5 avenue de la Gare",
            "postal_code": "75012",
            "city": "Paris",
            "latitude": 48.8443,
            "longitude": 2.3735,
        },
        "contract_type": ContractType.CDI,
    }


@pytest.fixture
def hca(hca_kwargs: Dict[str, Any]) -> Hca:
    """Return an unsaved assistant.

    Args:
        hca_kwargs (Dict[str, Any]): Constructor keyword arguments.

    Returns:
        Hca: An assistant with no identifier yet.
    """
    return Hca(company_id="company-1", **hca_kwargs)
