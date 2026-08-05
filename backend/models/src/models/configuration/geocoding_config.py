from __future__ import annotations

# Standard library imports
from typing import List, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator

# First-party imports
from models.configuration.exceptions import (
    MTGeocodingConfigInvalidBaseUrl,
    MTGeocodingConfigInvalidCountryCodes,
    MTGeocodingConfigInvalidTimeout,
    MTGeocodingConfigInvalidUserAgent,
)


class GeocodingConfig(BaseModel):
    """Settings for resolving a postal address to a coordinate via Nominatim.

    Attributes:
        base_url (str): The Nominatim search endpoint.
        user_agent (str): Identifying User-Agent sent with every request.
        timeout_seconds (float): Per-request timeout.
        country_codes (List[str]): ISO 3166-1 alpha-2 codes the search is
            restricted to. Empty searches worldwide.

    Notes:
        - Nominatim's usage policy requires a genuine identifying User-Agent and,
          on the public instance, at most one request per second. The User-Agent
          is configured and sent; the **rate is not throttled by this
          application**. A deployment that enters addresses in bulk should point
          ``base_url`` at its own Nominatim instance, or it risks having its
          address blocked by the public one.
        - Sending a generic or absent User-Agent gets an IP blocked, which
          presents as every address silently failing to geocode — so the field
          is required and validated rather than defaulted to something bland.
    """

    base_url: str = Field(
        default="https://nominatim.openstreetmap.org/search",
        description="The Nominatim search endpoint.",
    )
    user_agent: str = Field(
        default="rt-erp/0.1 (home-care planning; contact: ops@rt-erp.local)",
        description="Identifying User-Agent sent with every request.",
    )
    timeout_seconds: float = Field(
        default=10.0,
        description="Per-request timeout, in seconds.",
    )
    country_codes: List[str] = Field(
        default_factory=lambda: ["fr"],
        description="ISO 3166-1 alpha-2 codes the search is restricted to.",
    )

    @field_validator("base_url", mode="before")
    def validate_base_url(cls, value: Optional[str]) -> str:
        """Validates that ``base_url`` is an absolute HTTP URL.

        Args:
            value (Optional[str]): Raw ``base_url`` value.

        Returns:
            str: The URL without a trailing slash.

        Raises:
            MTGeocodingConfigInvalidBaseUrl: If ``value`` is not an ``http`` or
                ``https`` URL.
        """
        if not isinstance(value, str) or not value.strip().startswith(
            ("http://", "https://")
        ):
            raise MTGeocodingConfigInvalidBaseUrl(
                f"Invalid base_url: {value!r}. Must be an http or https URL."
            )
        return value.strip().rstrip("/")

    @field_validator("user_agent", mode="before")
    def validate_user_agent(cls, value: Optional[str]) -> str:
        """Validates that ``user_agent`` identifies the deployment.

        Args:
            value (Optional[str]): Raw ``user_agent`` value.

        Returns:
            str: The stripped User-Agent.

        Raises:
            MTGeocodingConfigInvalidUserAgent: If ``value`` is not a non-empty
                string.

        Notes:
            Nominatim blocks callers that do not identify themselves, and a
            blocked deployment sees every address fail to resolve with no
            obvious cause. Requiring the value here makes the omission a
            start-up error instead.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTGeocodingConfigInvalidUserAgent(
                f"Invalid user_agent: {value!r}. Must be a non-empty string "
                f"identifying this deployment, as Nominatim's usage policy "
                f"requires."
            )
        return value.strip()

    @field_validator("timeout_seconds", mode="before")
    def validate_timeout_seconds(cls, value: Union[int, float, str, None]) -> float:
        """Validates that ``timeout_seconds`` is strictly positive.

        Args:
            value (Union[int, float, str, None]): Raw timeout, in seconds.

        Returns:
            float: The validated timeout.

        Raises:
            MTGeocodingConfigInvalidTimeout: If ``value`` is not a strictly
                positive number.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MTGeocodingConfigInvalidTimeout(
                f"Invalid timeout_seconds: {value!r}. "
                f"Must be a strictly positive number of seconds."
            )
        coerced = float(value)
        if coerced <= 0:
            raise MTGeocodingConfigInvalidTimeout(
                f"Invalid timeout_seconds: {coerced!r}. Must be strictly positive."
            )
        return coerced

    @field_validator("country_codes", mode="before")
    def validate_country_codes(cls, value: JsonValue) -> List[str]:
        """Validates that ``country_codes`` holds ISO alpha-2 codes.

        Args:
            value (JsonValue): Raw list of country codes. ``None`` yields an
                empty list, which searches worldwide.

        Returns:
            List[str]: The lower-cased codes.

        Raises:
            MTGeocodingConfigInvalidCountryCodes: If ``value`` is neither
                ``None`` nor a list, or if an entry is not a two-letter code.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTGeocodingConfigInvalidCountryCodes(
                f"Invalid country_codes: {value!r}. Must be a list or None."
            )
        validated: List[str] = []
        for entry in value:
            if not isinstance(entry, str) or len(entry.strip()) != 2:
                raise MTGeocodingConfigInvalidCountryCodes(
                    f"Invalid country_codes entry: {entry!r}. "
                    f"Must be a two-letter ISO 3166-1 alpha-2 code."
                )
            validated.append(entry.strip().lower())
        return validated
