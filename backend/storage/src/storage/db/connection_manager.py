from __future__ import annotations

# Standard library imports
import asyncio
from contextlib import asynccontextmanager
from logging import Logger, getLogger
from typing import AsyncIterator, ClassVar, Dict, Optional

# Third-party imports
from sqlalchemy import text  # noqa: E501
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# First-party imports
from models.configuration.database_config import DatabaseConfig
from storage.db.exceptions import (
    MTDatabaseConnectionFailed,
    MTDatabaseNotConnected,
)


class DatabaseConnectionManager:
    """Owns the async engine and hands out sessions.

    Attributes:
        CONNECT_MAX_ATTEMPTS (ClassVar[int]): How many times ``connect`` retries
            before giving up.
        CONNECT_RETRY_DELAY_SECONDS (ClassVar[float]): Pause between attempts.
        CONNECT_ARGS (ClassVar[Dict[str, int]]): Driver arguments that make
            the engine safe behind a transaction-pooling PgBouncer.
        config (DatabaseConfig): The connection settings.
        logger (Logger): Logger for connection operations.
        engine (Optional[AsyncEngine]): The engine, once connected.
        session_factory (Optional[async_sessionmaker[AsyncSession]]): The
            session factory, once connected.

    Notes:
        - ``connect`` retries because the API and the database usually start
          together in a container stack: the first attempts fail while PostgreSQL
          is still booting, and treating that as fatal would make start-up order
          significant.
        - The connection URL carries the password, so only
          :attr:`DatabaseConfig.dsn_without_password` is ever logged.
    """

    CONNECT_MAX_ATTEMPTS: ClassVar[int] = 5
    CONNECT_RETRY_DELAY_SECONDS: ClassVar[float] = 2.0
    CONNECT_ARGS: ClassVar[Dict[str, int]] = {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }

    def __init__(self, config: DatabaseConfig, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Initialize the manager without opening a connection.

        Args:
            config (DatabaseConfig): The connection settings.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.

        Notes:
            Nothing is opened here. The engine is created by :meth:`connect`,
            so constructing a manager is safe outside an event loop.
        """
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self.connect_lock = asyncio.Lock()
        self.logger.debug(
            "DatabaseConnectionManager created for %s.",
            self.config.dsn_without_password,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    async def connect(self) -> None:
        """Open the engine and verify the database answers.

        Raises:
            MTDatabaseConnectionFailed: If every attempt failed.

        Notes:
            Guarded by a lock and idempotent: concurrent callers during
            start-up share one engine rather than racing to build several.
        """
        async with self.connect_lock:
            if self.engine is not None:
                self.logger.debug(
                    "Already connected. "  # noqa: E501
                    "Reusing the existing engine."
                )
                return
            self.logger.info("Connecting to %s.", self.config.dsn_without_password)  # noqa: E501
            last_error: Optional[Exception] = None
            for attempt in range(1, self.CONNECT_MAX_ATTEMPTS + 1):
                try:
                    engine = create_async_engine(
                        self.config.build_dsn(),
                        echo=self.config.echo_sql,
                        pool_size=self.config.pool_size,
                        max_overflow=self.config.max_overflow,
                        pool_timeout=self.config.pool_timeout_seconds,
                        pool_pre_ping=True,
                        connect_args=self.CONNECT_ARGS,
                    )
                    async with engine.connect() as connection:
                        await connection.execute(text("SELECT 1"))
                    self.engine = engine
                    self.session_factory = async_sessionmaker(
                        bind=engine,
                        expire_on_commit=False,
                    )
                    self.logger.info(
                        "Connected to %s on attempt %d.",
                        self.config.dsn_without_password,
                        attempt,
                    )
                    return
                except (SQLAlchemyError, OSError) as exc:
                    last_error = exc
                    self.logger.warning(
                        "Connection attempt %d/%d to %s failed: %s.",
                        attempt,
                        self.CONNECT_MAX_ATTEMPTS,
                        self.config.dsn_without_password,
                        exc,
                    )
                    if attempt < self.CONNECT_MAX_ATTEMPTS:
                        await asyncio.sleep(self.CONNECT_RETRY_DELAY_SECONDS)
            self.logger.error(
                "Giving up connecting to %s after %d attempts: %s.",
                self.config.dsn_without_password,
                self.CONNECT_MAX_ATTEMPTS,
                last_error,
            )
            raise MTDatabaseConnectionFailed(
                f"Failed to connect to {self.config.dsn_without_password} "
                f"after {self.CONNECT_MAX_ATTEMPTS} attempts: {last_error}."
            ) from last_error

    async def disconnect(self) -> None:
        """Dispose of the engine and release every pooled connection.

        Notes:
            Safe to call when never connected, so shutdown does not have to
            know whether start-up succeeded.
        """
        if self.engine is None:
            self.logger.debug("Disconnect requested but no engine is open.")
            return
        self.logger.info(
            "Disposing the engine for %s.", self.config.dsn_without_password
        )
        try:
            await self.engine.dispose()
        except SQLAlchemyError as exc:
            self.logger.error("Error disposing the engine: %s.", exc)
        finally:
            self.engine = None
            self.session_factory = None
            self.logger.debug("Engine disposed.")

    @property
    def is_connected(self) -> bool:
        """Return whether an engine is currently open.

        Returns:
            bool: ``True`` once :meth:`connect` has succeeded.
        """
        return self.engine is not None

    def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Return the session factory.

        Returns:
            async_sessionmaker[AsyncSession]: The factory bound to the engine.

        Raises:
            MTDatabaseNotConnected: If :meth:`connect` has not run.
        """
        if self.session_factory is None:
            self.logger.error("Session factory requested before connecting.")
            raise MTDatabaseNotConnected(
                "Not connected to the database. Call connect() first."
            )
        return self.session_factory

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session that commits on success and rolls back on error.

        Yields:
            AsyncSession: A session bound to the engine.

        Raises:
            MTDatabaseNotConnected: If :meth:`connect` has not run.

        Notes:
            The commit happens here rather than in each repository method, so a
            service that performs several writes gets them in one transaction
            instead of one per call.
        """
        factory = self.get_session_factory()
        session = factory()
        self.logger.debug("Opened a database session.")
        try:
            yield session
            await session.commit()
            self.logger.debug("Committed the database session.")
        except Exception as exc:
            await session.rollback()
            self.logger.error("Rolled back the database session: %s.", exc)
            raise
        finally:
            await session.close()

    async def ping(self) -> bool:
        """Return whether the database answers a trivial query.

        Returns:
            bool: ``True`` when the round-trip succeeded.

        Notes:
            Used by the readiness probe, so it reports rather than raises: a
            probe wants a status, not an exception.
        """
        if self.engine is None:
            self.logger.warning("Ping requested before connecting.")
            return False
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            self.logger.debug("Database ping succeeded.")
            return True
        except (SQLAlchemyError, OSError) as exc:
            self.logger.error("Database ping failed: %s.", exc)
            return False
