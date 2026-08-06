from __future__ import annotations

# Standard library imports
import os
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.configuration.exceptions import (
    MTEmailConfigInvalidAddress,
    MTEmailConfigInvalidEnvName,
    MTEmailConfigInvalidHost,
    MTEmailConfigInvalidPort,
)


class EmailConfig(BaseModel):
    """Settings for the outbound SMTP mailbox the backend sends from.

    Attributes:
        enabled (bool): Whether outbound email is active.
        host (str): SMTP server hostname.
        port (int): SMTP server port.
        use_tls (bool): Whether to issue STARTTLS before authenticating.
        sender (str): The ``From`` address stamped on outgoing messages.
        username_env (str): Name of the environment variable holding the SMTP
            username.
        password_env (str): Name of the environment variable holding the SMTP
            password.
        timeout_seconds (float): How long to wait on the SMTP conversation.

    Notes:
        - The credentials are **not** in the YAML. Each field holds the *name*
          of the environment variable carrying the value, resolved at send
          time, exactly as the database and authentication settings do. A
          configuration file lands in a repository; a mailbox password must
          not.
        - ``enabled`` exists so a developer's machine and the test suite never
          open an SMTP connection. Disabled, the service reports that it did
          not deliver rather than pretending it did — a planning that was
          never emailed must not look like one that was.
    """

    enabled: bool = Field(
        default=False,
        description="Whether outbound email is active.",
    )
    host: str = Field(
        default="smtp.gmail.com",
        description="SMTP server hostname.",
    )
    port: int = Field(
        default=587,
        description="SMTP server port.",
    )
    use_tls: bool = Field(
        default=True,
        description="Whether to issue STARTTLS before authenticating.",
    )
    sender: str = Field(
        default="planning@simple-erp.local",
        description="The From address stamped on outgoing messages.",
    )
    username_env: str = Field(
        default="SMTP_USERNAME",
        description="Name of the env var holding the SMTP username.",
    )
    password_env: str = Field(
        default="SMTP_PASSWORD",
        description="Name of the env var holding the SMTP password.",
    )
    timeout_seconds: float = Field(
        default=30.0,
        description="How long to wait on the SMTP conversation, in seconds.",
    )

    @field_validator("host", mode="before")
    def validate_host(cls, value: Optional[str]) -> str:
        """Validates that ``host`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``host`` value.

        Returns:
            str: The stripped hostname.

        Raises:
            MTEmailConfigInvalidHost: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTEmailConfigInvalidHost(
                f"Invalid host: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("port", mode="before")
    def validate_port(cls, value: Union[int, str, None]) -> int:
        """Validates that ``port`` is a usable TCP port.

        Args:
            value (Union[int, str, None]): Raw ``port`` value.

        Returns:
            int: The validated port.

        Raises:
            MTEmailConfigInvalidPort: If ``value`` is not an integer within
                ``1..65535``.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTEmailConfigInvalidPort(
                f"Invalid port: {value!r}. Must be an integer within 1..65535."
            )
        if not 1 <= value <= 65535:
            raise MTEmailConfigInvalidPort(
                f"Invalid port: {value!r}. Must be within 1..65535."
            )
        return value

    @field_validator("sender", mode="before")
    def validate_sender(cls, value: Optional[str]) -> str:
        """Validates that ``sender`` looks like an email address.

        Args:
            value (Optional[str]): Raw ``sender`` value.

        Returns:
            str: The stripped address.

        Raises:
            MTEmailConfigInvalidAddress: If ``value`` is not a non-empty string
                containing an ``@``.

        Notes:
            Deliberately not a full RFC check. The address is operator-supplied
            configuration, not user input, and the only failure worth catching
            at start-up is the obviously-wrong one.
        """
        if not isinstance(value, str) or "@" not in value.strip():
            raise MTEmailConfigInvalidAddress(
                f"Invalid sender: {value!r}. Must be an email address."
            )
        return value.strip()

    @field_validator("username_env", "password_env", mode="before")
    def validate_env_names(cls, value: Optional[str]) -> str:
        """Validates that a credential is named rather than inlined.

        Args:
            value (Optional[str]): Raw environment-variable name.

        Returns:
            str: The stripped name.

        Raises:
            MTEmailConfigInvalidEnvName: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTEmailConfigInvalidEnvName(
                f"Invalid environment variable name: {value!r}. Must be a "
                f"non-empty string naming the variable that holds the value."
            )
        return value.strip()

    ############################
    # Publicly Exposed Methods #
    ############################

    def get_username(self) -> str:
        """Return the SMTP username from the environment.

        Returns:
            str: The username, or an empty string when the variable is unset.
        """
        return os.environ.get(self.username_env, "")

    def get_password(self) -> str:
        """Return the SMTP password from the environment.

        Returns:
            str: The password, or an empty string when the variable is unset.

        Notes:
            Never logged, and never interpolated into an exception message.
        """
        return os.environ.get(self.password_env, "")

    def is_ready(self) -> bool:
        """Return whether a message can actually be sent.

        Returns:
            bool: ``True`` when outbound email is enabled and both credentials
            are present in the environment.
        """
        return bool(self.enabled and self.get_username() and self.get_password())
