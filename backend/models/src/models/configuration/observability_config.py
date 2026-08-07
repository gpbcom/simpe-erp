from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.configuration.exceptions import (
    MTObservabilityConfigInvalidEndpoint,
    MTObservabilityConfigInvalidFlag,
    MTObservabilityConfigInvalidPort,
    MTObservabilityConfigInvalidServiceName,
    MTObservabilityConfigInvalidTimeout,
)


class ObservabilityConfig(BaseModel):
    """Settings for what the process reports about itself.

    Attributes:
        MAX_PORT (ClassVar[int]): The highest usable TCP port.
        service_name (str): The name every metric, log line and span is grouped
            by. One per process kind, not one per deployment.
        metrics_enabled (bool): Whether ``/metrics`` is served.
        metrics_port (int): The port the worker serves its probes and metrics
            on. The API uses the port it already listens on.
        tracing_enabled (bool): Whether spans are exported.
        otlp_endpoint (str): Where spans are exported to.
        export_timeout_seconds (float): How long an export may take.

    Notes:
        - **Metrics and tracing switch independently.** Metrics are cheap and
          wanted everywhere, including on a laptop; tracing needs a collector to
          export to, and a process configured to export to one that is not there
          adds a failed connection to every request. So the local
          configuration turns the first on and the second off, and neither
          decision implies the other.
        - **The service name is a property of the *kind* of process**, not of
          the environment: ``simple-erp-api``, ``simple-erp-worker-planning``.
          The environment is a label the deployment adds, and putting it in here
          instead would make "API latency across staging and production" two
          series that cannot be compared.
        - There is no sampling rate here. It belongs to the collector, which
          sees every service's traffic and can decide consistently; a rate set
          per process produces traces that are complete for one hop and missing
          the next.
    """

    MAX_PORT: ClassVar[int] = 65535

    service_name: str = Field(
        default="simple-erp",
        description="What this process is called in metrics, logs and traces.",
    )
    metrics_enabled: bool = Field(
        default=True,
        description="Whether /metrics is served.",
    )
    metrics_port: int = Field(
        default=9100,
        description="Port the worker serves its probes and metrics on.",
    )
    tracing_enabled: bool = Field(
        default=False,
        description="Whether spans are exported over OTLP.",
    )
    otlp_endpoint: str = Field(
        default="http://localhost:4317",
        description="Where spans are exported to.",
    )
    export_timeout_seconds: float = Field(
        default=10.0,
        description="How long a span export may take, in seconds.",
    )

    @field_validator("metrics_enabled", "tracing_enabled", mode="before")
    def validate_flag(cls, value: Union[bool, str, int, None]) -> bool:
        """Validates that a switch is a real boolean.

        Args:
            value (Union[bool, str, int, None]): Raw switch value.

        Returns:
            bool: The validated switch.

        Raises:
            MTObservabilityConfigInvalidFlag: If ``value`` is not a boolean.

        Notes:
            A quoted ``"false"`` is truthy, so a lenient reading would export to
            a collector a file plainly says is disabled — and every span that
            failed to leave would cost a connection attempt on the request that
            produced it.
        """
        if not isinstance(value, bool):
            raise MTObservabilityConfigInvalidFlag(
                f"Invalid switch: {value!r}. Must be a boolean, not a string."
            )
        return value

    @field_validator("service_name", mode="before")
    def validate_service_name(cls, value: Optional[str]) -> str:
        """Validates that ``service_name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw service name.

        Returns:
            str: The stripped name.

        Raises:
            MTObservabilityConfigInvalidServiceName: If ``value`` is not a
                non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTObservabilityConfigInvalidServiceName(
                f"Invalid service_name: {value!r}. Must be a non-empty string "
                f"naming what this process is, such as 'simple-erp-api'."
            )
        return value.strip()

    @field_validator("otlp_endpoint", mode="before")
    def validate_otlp_endpoint(cls, value: Optional[str]) -> str:
        """Validates that ``otlp_endpoint`` is an absolute HTTP URL.

        Args:
            value (Optional[str]): Raw endpoint.

        Returns:
            str: The stripped endpoint.

        Raises:
            MTObservabilityConfigInvalidEndpoint: If ``value`` is not an
                absolute ``http://`` or ``https://`` URL.

        Notes:
            Checked even when tracing is off, so that turning it on is one flag
            rather than a flag and a restart to find out the endpoint was never
            valid.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTObservabilityConfigInvalidEndpoint(
                f"Invalid otlp_endpoint: {value!r}. Must be a non-empty string."
            )
        stripped = value.strip()
        if not stripped.startswith(("http://", "https://")):
            raise MTObservabilityConfigInvalidEndpoint(
                f"Invalid otlp_endpoint: {stripped!r}. "
                f"Must be an absolute http:// or https:// URL."
            )
        return stripped

    @field_validator("metrics_port", mode="before")
    def validate_metrics_port(cls, value: Union[int, str, None]) -> int:
        """Validates that ``metrics_port`` is a usable TCP port.

        Args:
            value (Union[int, str, None]): Raw port.

        Returns:
            int: The validated port.

        Raises:
            MTObservabilityConfigInvalidPort: If ``value`` is not an integer
                within ``1..65535``.

        Notes:
            Zero is refused rather than read as "pick one". A port the process
            chose at random is one nothing can be configured to scrape.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTObservabilityConfigInvalidPort(
                f"Invalid metrics_port: {value!r}. Must be an integer."
            )
        if not 1 <= value <= cls.MAX_PORT:
            raise MTObservabilityConfigInvalidPort(
                f"Invalid metrics_port: {value!r}. Must be within 1..{cls.MAX_PORT}."  # noqa: E501
            )
        return value

    @field_validator("export_timeout_seconds", mode="before")
    def validate_export_timeout(cls, value: Union[int, float, str, None]) -> float:  # noqa: E501
        """Validates that ``export_timeout_seconds`` is strictly positive.

        Args:
            value (Union[int, float, str, None]): Raw timeout, in seconds.

        Returns:
            float: The validated timeout.

        Raises:
            MTObservabilityConfigInvalidTimeout: If ``value`` is not a strictly
                positive number.

        Notes:
            A zero timeout is not "wait forever"; it fails the export
            immediately, and the only symptom is an empty trace view.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MTObservabilityConfigInvalidTimeout(
                f"Invalid export_timeout_seconds: {value!r}. Must be a number."
            )
        coerced = float(value)
        if coerced <= 0:
            raise MTObservabilityConfigInvalidTimeout(
                f"Invalid export_timeout_seconds: {coerced!r}. "
                f"Must be strictly positive."
            )
        return coerced

    def named(self, suffix: str) -> ObservabilityConfig:
        """Return a copy naming one particular process.

        Args:
            suffix (str): What this process is, such as ``worker-planning``.

        Returns:
            ObservabilityConfig: A copy whose ``service_name`` carries the
            suffix.

        Notes:
            The configuration file carries the *application's* name and each
            entry point adds what it is, so the four processes that share one
            image and one configuration file do not share one series. Doing it
            the other way — a name per process in the file — would mean four
            files, or one file the entry points each had to ignore most of.
        """
        return self.model_copy(update={"service_name": f"{self.service_name}-{suffix}"})  # noqa: E501
