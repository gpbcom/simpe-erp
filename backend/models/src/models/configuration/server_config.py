from __future__ import annotations

# Standard library imports
from typing import ClassVar, List, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator

# First-party imports
from models.configuration.exceptions import (
    MTServerConfigInvalidCorsOrigins,
    MTServerConfigInvalidHost,
    MTServerConfigInvalidPort,
)


class ServerConfig(BaseModel):
    """Settings governing how the HTTP server binds and answers.

    Attributes:
        MAX_PORT (ClassVar[int]): Highest valid TCP port number.
        host (str): Interface to bind to. Defaults to ``"0.0.0.0"``.
        port (int): Port to listen on. Defaults to ``8000``.
        cors_origins (List[str]): Origins allowed by the CORS middleware.
        title (str): Title shown in the generated OpenAPI document.
        version (str): Version shown in the generated OpenAPI document.

    Notes:
        ``cors_origins`` defaults to an empty list rather than to ``["*"]``. A
        permissive default combined with credentialed requests would let any
        site drive the API with a logged-in user's token; the deployment must
        name its front-end explicitly.
    """

    MAX_PORT: ClassVar[int] = 65535

    host: str = Field(default="0.0.0.0", description="Interface to bind to.")
    port: int = Field(default=8000, description="Port to listen on.")
    cors_origins: List[str] = Field(
        default_factory=list,
        description="Origins allowed by the CORS middleware.",
    )
    title: str = Field(
        default="SimpleERP API",
        description="Title shown in the generated OpenAPI document.",
    )
    version: str = Field(
        default="1.0.0",
        description="Version shown in the generated OpenAPI document.",
    )

    @field_validator("host", "title", "version", mode="before")
    def validate_non_empty_text(cls, value: Optional[str]) -> str:
        """Validates that a text field is a non-empty string.

        Args:
            value (Optional[str]): Raw text value.

        Returns:
            str: The stripped text.

        Raises:
            MTServerConfigInvalidHost: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTServerConfigInvalidHost(
                f"Invalid value: {value!r}. Must be a non-empty string."
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
            MTServerConfigInvalidPort: If ``value`` is not an integer within
                ``1..65535``.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTServerConfigInvalidPort(
                f"Invalid port: {value!r}. Must be an integer within 1..{cls.MAX_PORT}."
            )
        if not 1 <= value <= cls.MAX_PORT:
            raise MTServerConfigInvalidPort(
                f"Invalid port: {value!r}. Must be within 1..{cls.MAX_PORT}."
            )
        return value

    @field_validator("cors_origins", mode="before")
    def validate_cors_origins(cls, value: JsonValue) -> List[str]:
        """Validates that ``cors_origins`` is a list of non-empty strings.

        Args:
            value (JsonValue): Raw list of allowed origins. ``None`` yields an
                empty list.

        Returns:
            List[str]: The validated, stripped origins.

        Raises:
            MTServerConfigInvalidCorsOrigins: If ``value`` is neither ``None``
                nor a list, or if an entry is not a non-empty string.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTServerConfigInvalidCorsOrigins(
                f"Invalid cors_origins: {value!r}. Must be a list or None."
            )
        validated: List[str] = []
        for origin in value:
            if not isinstance(origin, str) or not origin.strip():
                raise MTServerConfigInvalidCorsOrigins(
                    f"Invalid cors_origins entry: {origin!r}. "
                    f"Must be a non-empty string."
                )
            validated.append(origin.strip())
        return validated
