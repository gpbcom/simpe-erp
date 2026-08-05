"""Alembic environment for the async PostgreSQL engine.

Notes:
    The connection URL is taken from ``AppConfig`` rather than from
    ``alembic.ini``, so the database password lives only in the environment and
    never in a file under version control.

    The engine is async, so the migrations run inside ``connection.run_sync``:
    Alembic's migration context is synchronous and cannot drive an async
    connection directly.
"""

from __future__ import annotations

# Standard library imports
import asyncio
from logging.config import fileConfig

# Third-party imports
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# First-party imports
from models.configuration.app_config import AppConfig
from storage.orm import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

app_config = AppConfig.load()
config.set_main_option("sqlalchemy.url", app_config.database.build_dsn())


def run_migrations_offline() -> None:
    """Emit the migration SQL without connecting to a database.

    Notes:
        Used to review a migration before it is applied, so no credential is
        needed and no statement is executed.
    """
    context.configure(
        url=app_config.database.build_dsn(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run the migrations on an already-open synchronous connection.

    Args:
        connection (Connection): The synchronous facade handed over by
            ``run_sync``.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Open the async engine and run the migrations through it."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run the migrations against the configured database."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
