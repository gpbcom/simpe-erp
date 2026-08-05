from __future__ import annotations

# Standard library imports
import os
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, computed_field, field_validator

# First-party imports
from models.configuration.exceptions import (
    MTDatabaseConfigInvalidDatabase,
    MTDatabaseConfigInvalidHost,
    MTDatabaseConfigInvalidPasswordEnv,
    MTDatabaseConfigInvalidPoolSize,
    MTDatabaseConfigInvalidPort,
    MTDatabaseConfigInvalidUsername,
    MTDatabaseConfigMissingPassword,
)


class DatabaseConfig(BaseModel):
    """Connection settings for the PostgreSQL database.

    Attributes:
        DRIVER (ClassVar[str]): The SQLAlchemy dialect and driver used to build
            the connection URL.
        MAX_PORT (ClassVar[int]): Highest valid TCP port number.
        host (str): Database host name.
        port (int): Database port. Defaults to ``5432``.
        database (str): Database name.
        username (str): Role to connect as.
        password_env (str): Name of the environment variable holding the
            password. The password itself is never stored in configuration.
        pool_size (int): Number of connections kept open in the pool.
        max_overflow (int): Extra connections the pool may open under load.
        pool_timeout_seconds (float): How long to wait for a free connection.
        echo_sql (bool): Whether SQLAlchemy should log every statement.

    Notes:
        ``password_env`` names an environment variable rather than carrying the
        secret, so the configuration file stays safe to commit. Resolution
        happens in :meth:`get_password`, at connection time, so a missing
        secret fails where it can be reported rather than at import time.
    """

    DRIVER: ClassVar[str] = "postgresql+asyncpg"
    MAX_PORT: ClassVar[int] = 65535

    host: str = Field(default="localhost", description="Database host name.")
    port: int = Field(default=5432, description="Database port.")
    database: str = Field(default="rt_erp", description="Database name.")
    username: str = Field(default="rt_erp", description="Role to connect as.")
    password_env: str = Field(
        default="POSTGRES_PASSWORD",
        description="Name of the environment variable holding the password.",
    )
    pool_size: int = Field(default=10, description="Connections kept in the pool.")
    max_overflow: int = Field(default=5, description="Extra connections under load.")
    pool_timeout_seconds: float = Field(
        default=30.0,
        description="How long to wait for a free connection, in seconds.",
    )
    echo_sql: bool = Field(
        default=False,
        description="Whether SQLAlchemy should log every statement.",
    )

    @field_validator("host", mode="before")
    def validate_host(cls, value: Optional[str]) -> str:
        """Validates that ``host`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``host`` value.

        Returns:
            str: The stripped host name.

        Raises:
            MTDatabaseConfigInvalidHost: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTDatabaseConfigInvalidHost(
                f"Invalid host: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("port", mode="before")
    def validate_port(cls, value: Union[int, str]) -> int:
        """Validates that ``port`` is a valid TCP port number.

        Args:
            value (Union[int, str]): Raw ``port`` value.

        Returns:
            int: The validated port.

        Raises:
            MTDatabaseConfigInvalidPort: If ``value`` is not an integer within
                ``1..65535``.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTDatabaseConfigInvalidPort(
                f"Invalid port: {value!r}. Must be an integer within 1..{cls.MAX_PORT}."
            )
        if not 1 <= value <= cls.MAX_PORT:
            raise MTDatabaseConfigInvalidPort(
                f"Invalid port: {value!r}. Must be within 1..{cls.MAX_PORT}."
            )
        return value

    @field_validator("database", mode="before")
    def validate_database(cls, value: Optional[str]) -> str:
        """Validates that ``database`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``database`` value.

        Returns:
            str: The stripped database name.

        Raises:
            MTDatabaseConfigInvalidDatabase: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTDatabaseConfigInvalidDatabase(
                f"Invalid database: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("username", mode="before")
    def validate_username(cls, value: Optional[str]) -> str:
        """Validates that ``username`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``username`` value.

        Returns:
            str: The stripped user name.

        Raises:
            MTDatabaseConfigInvalidUsername: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTDatabaseConfigInvalidUsername(
                f"Invalid username: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("password_env", mode="before")
    def validate_password_env(cls, value: Optional[str]) -> str:
        """Validates that ``password_env`` names an environment variable.

        Args:
            value (Optional[str]): Raw ``password_env`` value.

        Returns:
            str: The stripped environment-variable name.

        Raises:
            MTDatabaseConfigInvalidPasswordEnv: If ``value`` is not a non-empty
                string.

        Notes:
            Only the *name* is validated here. Whether the variable is actually
            set is a runtime question, answered by :meth:`get_password`.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTDatabaseConfigInvalidPasswordEnv(
                f"Invalid password_env: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("pool_size", "max_overflow", mode="before")
    def validate_pool_sizing(cls, value: Union[int, str]) -> int:
        """Validates that a pool-sizing field is a non-negative integer.

        Args:
            value (Union[int, str]): Raw pool-sizing value.

        Returns:
            int: The validated value.

        Raises:
            MTDatabaseConfigInvalidPoolSize: If ``value`` is not a non-negative
                integer.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTDatabaseConfigInvalidPoolSize(
                f"Invalid pool sizing: {value!r}. Must be a non-negative integer."
            )
        if value < 0:
            raise MTDatabaseConfigInvalidPoolSize(
                f"Invalid pool sizing: {value!r}. Must be non-negative."
            )
        return value

    @field_validator("pool_timeout_seconds", mode="before")
    def validate_pool_timeout_seconds(cls, value: Union[int, float, str]) -> float:  # noqa: E501
        """Validates that ``pool_timeout_seconds`` is strictly positive.

        Args:
            value (Union[int, float, str]): Raw timeout value, in seconds.

        Returns:
            float: The validated timeout.

        Raises:
            MTDatabaseConfigInvalidPoolTimeout: If ``value`` is not a strictly
                positive real number.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MTDatabaseConfigInvalidPoolSize(
                f"Invalid pool_timeout_seconds: {value!r}. "
                f"Must be a strictly positive number of seconds."
            )
        coerced = float(value)
        if coerced <= 0:
            raise MTDatabaseConfigInvalidPoolSize(
                f"Invalid pool_timeout_seconds: {coerced!r}. Must be strictly positive."
            )
        return coerced

    ############################
    # Publicly Exposed Methods #
    ############################

    @computed_field
    @property
    def dsn_without_password(self) -> str:
        """Return the connection URL with the password left out.

        Returns:
            str: A SQLAlchemy async URL safe to log.

        Notes:
            This is the form that goes into log lines and error messages. The
            complete URL is built by :meth:`build_dsn`, which is never logged.
        """
        return (
            f"{self.DRIVER}://{self.username}@{self.host}:{self.port}/{self.database}"  # noqa: E501
        )

    def get_password(self) -> str:
        """Return the database password from the environment.

        Returns:
            str: The resolved password.

        Raises:
            MTDatabaseConfigMissingPassword: If the environment variable named
                by ``password_env`` is unset or empty.
        """
        password = os.environ.get(self.password_env, "")
        if not password:
            raise MTDatabaseConfigMissingPassword(
                f"Environment variable {self.password_env!r} is not set. "
                f"It must hold the password for {self.dsn_without_password}."
            )
        return password

    def build_dsn(self) -> str:
        """Return the complete SQLAlchemy async connection URL.

        Returns:
            str: The connection URL, password included.

        Raises:
            MTDatabaseConfigMissingPassword: If the password environment
                variable is unset or empty.

        Notes:
            The return value carries a secret. It must be handed straight to
            the engine factory and never logged; log
            :attr:`dsn_without_password` instead.
        """
        return (
            f"{self.DRIVER}://{self.username}:{self.get_password()}@"
            f"{self.host}:{self.port}/{self.database}"
        )
