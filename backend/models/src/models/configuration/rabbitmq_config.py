from __future__ import annotations

# Standard library imports
import os
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.configuration.exceptions import (
    MTRabbitMqConfigInvalidEnvName,
    MTRabbitMqConfigInvalidExchange,
    MTRabbitMqConfigInvalidHost,
    MTRabbitMqConfigInvalidPort,
    MTRabbitMqConfigInvalidTimeout,
)


class RabbitMqConfig(BaseModel):
    """Settings for the message broker carrying the agency's events.

    Attributes:
        enabled (bool): Whether events are published at all.
        host (str): The broker's hostname.
        port (int): The broker's AMQP port.
        virtual_host (str): The virtual host to connect to.
        username (str): The account to connect as.
        password_env (str): Name of the environment variable holding the
            password.
        exchange (str): The topic exchange every event is published to.
        publish_timeout_seconds (float): How long a publish may block.
        prefetch (int): How many messages a consumer takes at once.

    Notes:
        - ``enabled`` defaults to **false**, matching the email section. A
          developer running the API alone must not have every quote submission
          fail because there is no broker on their machine; the event is logged
          and dropped instead.
        - The password is named rather than stored, like every other secret in
          this configuration. The value is read at connection time so a rotated
          secret needs a restart rather than a rebuild.
        - ``prefetch`` is one by default because the heaviest consumer runs an
          OR-Tools solve, which pins a core for its whole budget. Taking a
          second message while the first is solving would not make it finish
          sooner; it would only delay the acknowledgement of both.
    """

    enabled: bool = Field(
        default=False,
        description="Whether events are published to the broker.",
    )
    host: str = Field(default="localhost", description="The broker's hostname.")
    port: int = Field(default=5672, description="The broker's AMQP port.")
    virtual_host: str = Field(default="/", description="The virtual host.")
    username: str = Field(default="rt_erp", description="The account to use.")
    password_env: str = Field(
        default="RABBITMQ_PASSWORD",
        description="Name of the env var holding the password.",
    )
    exchange: str = Field(
        default="rt-erp",
        description="The topic exchange every event is published to.",
    )
    publish_timeout_seconds: float = Field(
        default=5.0,
        description="How long a publish may block, in seconds.",
    )
    prefetch: int = Field(
        default=1,
        description="How many messages a consumer takes at once.",
    )

    @field_validator("host", mode="before")
    def validate_host(cls, value: Optional[str]) -> str:
        """Validates that ``host`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``host`` value.

        Returns:
            str: The stripped hostname.

        Raises:
            MTRabbitMqConfigInvalidHost: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTRabbitMqConfigInvalidHost(
                f"Invalid host: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("port", mode="before")
    def validate_port(cls, value: Union[int, str, None]) -> int:
        """Validates that ``port`` is inside the TCP range.

        Args:
            value (Union[int, str, None]): Raw ``port`` value.

        Returns:
            int: The port number.

        Raises:
            MTRabbitMqConfigInvalidPort: If ``value`` is not an integer between
                1 and 65535.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTRabbitMqConfigInvalidPort(
                f"Invalid port: {value!r}. Must be an integer."
            )
        if not 1 <= value <= 65535:
            raise MTRabbitMqConfigInvalidPort(
                f"Invalid port: {value!r}. Must be between 1 and 65535."
            )
        return value

    @field_validator("exchange", "virtual_host", "username", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that a broker name is a non-empty string.

        Args:
            value (Optional[str]): Raw value.

        Returns:
            str: The stripped value.

        Raises:
            MTRabbitMqConfigInvalidExchange: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTRabbitMqConfigInvalidExchange(
                f"Invalid broker name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("password_env", mode="before")
    def validate_password_env(cls, value: Optional[str]) -> str:
        """Validates that ``password_env`` names an environment variable.

        Args:
            value (Optional[str]): Raw ``password_env`` value.

        Returns:
            str: The stripped variable name.

        Raises:
            MTRabbitMqConfigInvalidEnvName: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTRabbitMqConfigInvalidEnvName(
                f"Invalid password_env: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("publish_timeout_seconds", mode="before")
    def validate_timeout(cls, value: Union[int, float, None]) -> float:
        """Validates that the publish timeout is a positive number.

        Args:
            value (Union[int, float, None]): Raw timeout value.

        Returns:
            float: The timeout, in seconds.

        Raises:
            MTRabbitMqConfigInvalidTimeout: If ``value`` is not a positive
                number.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MTRabbitMqConfigInvalidTimeout(
                f"Invalid publish_timeout_seconds: {value!r}. Must be a number."
            )
        if value <= 0:
            raise MTRabbitMqConfigInvalidTimeout(
                f"Invalid publish_timeout_seconds: {value!r}. Must be positive."
            )
        return float(value)

    @field_validator("prefetch", mode="before")
    def validate_prefetch(cls, value: Union[int, str, None]) -> int:
        """Validates that ``prefetch`` is a positive integer.

        Args:
            value (Union[int, str, None]): Raw ``prefetch`` value.

        Returns:
            int: The prefetch count.

        Raises:
            MTRabbitMqConfigInvalidPort: If ``value`` is not a positive
                integer.
        """
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise MTRabbitMqConfigInvalidPort(
                f"Invalid prefetch: {value!r}. Must be a positive integer."
            )
        return value

    def get_password(self) -> str:
        """Return the broker password from the environment.

        Returns:
            str: The password, or an empty string when the variable is unset.

        Notes:
            An absent password is returned as empty rather than raised on,
            because a development broker may genuinely have none. The
            connection failure that follows names the broker, which is more use
            than a configuration error naming the variable.
        """
        return os.getenv(self.password_env, "")

    def build_url(self) -> str:
        """Return the AMQP URL to connect with.

        Returns:
            str: The full ``amqp://`` URL, password included.

        Notes:
            Never logged. Use :meth:`url_without_password` for anything that is
            written down.
        """
        return (
            f"amqp://{self.username}:{self.get_password()}"
            f"@{self.host}:{self.port}/{self.virtual_host.lstrip('/')}"
        )

    def url_without_password(self) -> str:
        """Return the AMQP URL with the password masked.

        Returns:
            str: The URL, safe to log.

        Notes:
            Exists so that "could not reach the broker" can name *which* broker
            without putting the credential in a log file — the same trade the
            database configuration makes.
        """
        return (
            f"amqp://{self.username}:***"
            f"@{self.host}:{self.port}/{self.virtual_host.lstrip('/')}"
        )
