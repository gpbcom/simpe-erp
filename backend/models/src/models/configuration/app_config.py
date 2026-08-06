from __future__ import annotations

# Standard library imports
import os
from pathlib import Path
from typing import ClassVar, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator
import yaml

# First-party imports
from models.configuration.auth_config import AuthConfig
from models.configuration.database_config import DatabaseConfig
from models.configuration.email_config import EmailConfig
from models.configuration.exceptions import (
    MTAppConfigInvalidAuth,
    MTAppConfigInvalidDatabase,
    MTAppConfigInvalidGeocoding,
    MTAppConfigInvalidPlanning,
    MTAppConfigInvalidPricing,
    MTAppConfigInvalidRabbitMq,
    MTAppConfigInvalidS3,
    MTAppConfigInvalidServer,
    MTAppConfigNotFound,
    MTAppConfigUnreadable,
)
from models.configuration.geocoding_config import GeocodingConfig
from models.configuration.planning_config import PlanningConfig
from models.configuration.pricing_config import PricingConfig
from models.configuration.rabbitmq_config import RabbitMqConfig
from models.configuration.s3_config import S3Config
from models.configuration.server_config import ServerConfig
from models.configuration.webhook_config import WebhookConfig


class AppConfig(BaseModel):
    """The whole backend configuration, as loaded from ``conf/app.yaml``.

    Attributes:
        CONFIG_PATH_ENV (ClassVar[str]): Environment variable naming the file
            to load, consulted before the default path.
        DEFAULT_CONFIG_PATH (ClassVar[str]): Path the loader falls back to when
            none is supplied.
        server (ServerConfig): HTTP server settings.
        database (DatabaseConfig): PostgreSQL connection settings.
        auth (AuthConfig): Authentication and token-issuance settings.
        pricing (PricingConfig): Quote pricing rules.
        planning (PlanningConfig): Planning-computation parameters.
        geocoding (GeocodingConfig): Nominatim geocoding settings.
        email (EmailConfig): Outbound SMTP settings.
        webhook (WebhookConfig): Settings for the planning-completed webhook.
        s3 (S3Config): Object-store settings for assistant photographs.
        rabbitmq (RabbitMqConfig): Message-broker settings.

    Notes:
        Every section carries a default, so an absent section in the YAML file
        yields its documented defaults rather than an error. That keeps the
        configuration file small: it needs to state only what deviates.
    """

    CONFIG_PATH_ENV: ClassVar[str] = "SIMPLE_ERP_CONFIG"
    DEFAULT_CONFIG_PATH: ClassVar[str] = "conf/app.yaml"

    server: ServerConfig = Field(
        default_factory=ServerConfig,
        description="HTTP server settings.",
    )
    database: DatabaseConfig = Field(
        default_factory=DatabaseConfig,
        description="PostgreSQL connection settings.",
    )
    auth: AuthConfig = Field(
        default_factory=AuthConfig,
        description="Authentication and token-issuance settings.",
    )
    pricing: PricingConfig = Field(
        default_factory=PricingConfig,
        description="Quote pricing rules.",
    )
    planning: PlanningConfig = Field(
        default_factory=PlanningConfig,
        description="Planning-computation parameters.",
    )
    geocoding: GeocodingConfig = Field(
        default_factory=GeocodingConfig,
        description="Nominatim geocoding settings.",
    )
    email: EmailConfig = Field(
        default_factory=EmailConfig,
        description="Outbound SMTP settings.",
    )
    webhook: WebhookConfig = Field(
        default_factory=WebhookConfig,
        description="Settings for the planning-completed webhook.",
    )
    rabbitmq: RabbitMqConfig = Field(
        default_factory=RabbitMqConfig,
        description="Message-broker settings.",
    )
    s3: S3Config = Field(
        default_factory=S3Config,
        description="Object-store settings for assistant photographs.",
    )

    @field_validator("server", mode="before")
    def validate_server(cls, value: JsonValue) -> JsonValue:
        """Validates that ``server`` is a mapping or an already-built section.

        Args:
            value (JsonValue): Raw ``server`` payload.

        Returns:
            JsonValue: The payload handed back for Pydantic to build.

        Raises:
            MTAppConfigInvalidServer: If ``value`` is neither a mapping nor a
                :class:`~models.configuration.server_config.ServerConfig`.
        """
        if value is None:
            return {}
        if not isinstance(value, (ServerConfig, dict)):
            raise MTAppConfigInvalidServer(
                f"Invalid server section: {value!r}. Must be a mapping."
            )
        return value

    @field_validator("database", mode="before")
    def validate_database(cls, value: JsonValue) -> JsonValue:
        """Validates that ``database`` is a mapping or an already-built section.

        Args:
            value (JsonValue): Raw ``database`` payload.

        Returns:
            JsonValue: The payload handed back for Pydantic to build.

        Raises:
            MTAppConfigInvalidDatabase: If ``value`` is neither a mapping nor a
                :class:`~models.configuration.database_config.DatabaseConfig`.
        """
        if value is None:
            return {}
        if not isinstance(value, (DatabaseConfig, dict)):
            raise MTAppConfigInvalidDatabase(
                f"Invalid database section: {value!r}. Must be a mapping."
            )
        return value

    @field_validator("auth", mode="before")
    def validate_auth(cls, value: JsonValue) -> JsonValue:
        """Validates that ``auth`` is a mapping or an already-built section.

        Args:
            value (JsonValue): Raw ``auth`` payload.

        Returns:
            JsonValue: The payload handed back for Pydantic to build.

        Raises:
            MTAppConfigInvalidAuth: If ``value`` is neither a mapping nor an
                :class:`~models.configuration.auth_config.AuthConfig`.
        """
        if value is None:
            return {}
        if not isinstance(value, (AuthConfig, dict)):
            raise MTAppConfigInvalidAuth(
                f"Invalid auth section: {value!r}. Must be a mapping."
            )
        return value

    @field_validator("pricing", mode="before")
    def validate_pricing(cls, value: JsonValue) -> JsonValue:
        """Validates that ``pricing`` is a mapping or an already-built section.

        Args:
            value (JsonValue): Raw ``pricing`` payload.

        Returns:
            JsonValue: The payload handed back for Pydantic to build.

        Raises:
            MTAppConfigInvalidPricing: If ``value`` is neither a mapping nor a
                :class:`~models.configuration.pricing_config.PricingConfig`.
        """
        if value is None:
            return {}
        if not isinstance(value, (PricingConfig, dict)):
            raise MTAppConfigInvalidPricing(
                f"Invalid pricing section: {value!r}. Must be a mapping."
            )
        return value

    @field_validator("planning", mode="before")
    def validate_planning(cls, value: JsonValue) -> JsonValue:
        """Validates that ``planning`` is a mapping or an already-built section.

        Args:
            value (JsonValue): Raw ``planning`` payload.

        Returns:
            JsonValue: The payload handed back for Pydantic to build.

        Raises:
            MTAppConfigInvalidPlanning: If ``value`` is neither a mapping nor a
                :class:`~models.configuration.planning_config.PlanningConfig`.
        """
        if value is None:
            return {}
        if not isinstance(value, (PlanningConfig, dict)):
            raise MTAppConfigInvalidPlanning(
                f"Invalid planning section: {value!r}. Must be a mapping."
            )
        return value

    @field_validator("geocoding", mode="before")
    def validate_geocoding(cls, value: JsonValue) -> JsonValue:
        """Validates that ``geocoding`` is a mapping or an already-built section.

        Args:
            value (JsonValue): Raw ``geocoding`` payload.

        Returns:
            JsonValue: The payload handed back for Pydantic to build.

        Raises:
            MTAppConfigInvalidGeocoding: If ``value`` is neither a mapping nor a
                :class:`~models.configuration.geocoding_config.GeocodingConfig`.
        """
        if value is None:
            return {}
        if not isinstance(value, (GeocodingConfig, dict)):
            raise MTAppConfigInvalidGeocoding(
                f"Invalid geocoding section: {value!r}. Must be a mapping."
            )
        return value

    @field_validator("rabbitmq", mode="before")
    def validate_rabbitmq(cls, value: JsonValue) -> JsonValue:
        """Validates that ``rabbitmq`` is a mapping or an already-built section.

        Args:
            value (JsonValue): Raw ``rabbitmq`` payload.

        Returns:
            JsonValue: The payload handed back for Pydantic to build.

        Raises:
            MTAppConfigInvalidRabbitMq: If ``value`` is neither a mapping nor a
                :class:`~models.configuration.rabbitmq_config.RabbitMqConfig`.
        """
        if not isinstance(value, (RabbitMqConfig, dict)):
            raise MTAppConfigInvalidRabbitMq(
                f"Invalid rabbitmq section: {value!r}. Must be a mapping."
            )
        return value

    @field_validator("s3", mode="before")
    def validate_s3(cls, value: JsonValue) -> JsonValue:
        """Validates that ``s3`` is a mapping or an already-built section.

        Args:
            value (JsonValue): Raw ``s3`` payload.

        Returns:
            JsonValue: The payload handed back for Pydantic to build.

        Raises:
            MTAppConfigInvalidS3: If ``value`` is neither a mapping nor an
                :class:`~models.configuration.s3_config.S3Config`.
        """
        if value is None:
            return {}
        if not isinstance(value, (S3Config, dict)):
            raise MTAppConfigInvalidS3(
                f"Invalid s3 section: {value!r}. Must be a mapping."
            )
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    @classmethod
    def load(cls, config_path: Union[str, Path, None] = None) -> AppConfig:
        """Load and validate the configuration from a YAML file.

        Args:
            config_path (Union[str, Path, None]): Path to the YAML file.
                ``None`` uses ``$SIMPLE_ERP_CONFIG``, then
                :attr:`DEFAULT_CONFIG_PATH`.

        Returns:
            AppConfig: The validated configuration.

        Raises:
            MTAppConfigNotFound: If no file exists at either the supplied path
                or the package-relative fallback.
            MTAppConfigUnreadable: If the file cannot be read or does not parse
                as a YAML mapping.

        Notes:
            - When the supplied path does not resolve against the current working
              directory, it is retried relative to the backend project root. The
              test suite and the container run from different directories, and
              without the fallback the configuration would load in one and not
              the other.
            - ``$SIMPLE_ERP_CONFIG`` selects the file when no path is passed. A
              container reaches PostgreSQL and MinIO by service name where a
              developer's machine reaches them on localhost, and the difference
              spans several keys rather than one — pointing at a whole file keeps
              a deployment from editing the checked-in configuration in place.
            - Reading it here rather than at each entry point matters: the
              application and the Alembic environment both load configuration,
              and honouring the variable in only one of them would migrate one
              database while serving another.
        """
        selected = config_path if config_path else os.getenv(cls.CONFIG_PATH_ENV)
        resolved = Path(selected if selected else cls.DEFAULT_CONFIG_PATH)
        if not resolved.exists():
            project_root = Path(__file__).resolve().parents[4]
            fallback = project_root / resolved
            if not fallback.exists():
                raise MTAppConfigNotFound(
                    f"No configuration file at {resolved} or {fallback}."
                )
            resolved = fallback
        try:
            with open(resolved, "r", encoding="utf-8") as config_file:
                payload = yaml.safe_load(config_file)
        except (OSError, yaml.YAMLError) as exc:
            raise MTAppConfigUnreadable(
                f"Failed to read the configuration at {resolved}: {exc}."
            ) from exc
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise MTAppConfigUnreadable(
                f"Invalid configuration at {resolved}: "
                f"the document must be a mapping, got {type(payload).__name__}."
            )
        return cls.model_validate(payload)
