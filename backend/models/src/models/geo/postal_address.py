from __future__ import annotations

# Standard library imports
import json
from logging import getLogger
from typing import ClassVar, Dict, Optional, Tuple, Union
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator

# First-party imports
from models.geo.exceptions import (
    MTPostalAddressGeocodingFailed,
    MTPostalAddressInvalidCity,
    MTPostalAddressInvalidCountry,
    MTPostalAddressInvalidGeocodingError,
    MTPostalAddressInvalidLatitude,
    MTPostalAddressInvalidLongitude,
    MTPostalAddressInvalidPostalCode,
    MTPostalAddressInvalidResponse,
    MTPostalAddressInvalidStreet,
    MTPostalAddressNotFound,
)
from models.geo.geo_point import GeoPoint


class PostalAddress(BaseModel):
    """A postal address, optionally resolved to a geographic coordinate.

    Attributes:
        VALID_GEOCODING_ERRORS (ClassVar[Tuple[str, ...]]): The stable codes
            that ``geocoding_error`` accepts.
        DEFAULT_COUNTRY (ClassVar[str]): Country used when none is supplied.
        street (str): Street line, including the number.
        postal_code (str): Postal code.
        city (str): City, town or village.
        country (str): Country name. Defaults to ``"France"``.
        latitude (Optional[float]): Resolved latitude in decimal degrees, or
            ``None`` while the address has not been geocoded.
        longitude (Optional[float]): Resolved longitude in decimal degrees, or
            ``None`` while the address has not been geocoded.
        geocoding_error (Optional[str]): Stable code naming a non-fatal
            geocoding failure, or ``None`` when the last attempt succeeded or
            none was made.

    Notes:
        - Constructing an address **resolves its coordinate through Nominatim**
          when it is not already resolved. The lookup happens in
          :meth:`model_post_init`, so an address is never half-built: what comes
          out either carries a coordinate or carries a stable code saying why it
          does not.
        - What counts as *already resolved* is the whole safety mechanism.
          :meth:`_is_resolved` answers yes to both an address carrying a
          coordinate **and** one carrying a ``geocoding_error``, and every
          address that has been through this class carries one or the other.
          Re-hydrating a stored row therefore never calls out — including the
          rows the geocoder could not place, which are exactly the ones a
          naive "no coordinate, look it up" rule would retry on every single
          read, one blocking request per row inside an async handler.
        - A retry is a deliberate act: clear ``geocoding_error`` and rebuild the
          address. Nothing retries by accident.
        - Every failure becomes a stable ``geocoding_error`` code rather than an
          exception. An address the geocoder does not know must still be
          storable: the quote has to be printable either way, and the missing
          coordinate resurfaces later as an unassignable planning requirement.
        - Nominatim's usage policy caps the public instance at one request per
          second. Nothing here throttles: a bulk import that creates addresses
          in a loop must space its own calls, or point
          :attr:`GEOCODE_URL` at a self-hosted instance.
    """

    VALID_GEOCODING_ERRORS: ClassVar[Tuple[str, ...]] = (
        "service_unavailable",
        "not_found",
        "invalid_response",
    )
    DEFAULT_COUNTRY: ClassVar[str] = "France"

    GEOCODE_URL: ClassVar[str] = "https://nominatim.openstreetmap.org/search"
    USER_AGENT: ClassVar[str] = (
        "simple-erp/0.1 (home-care planning; contact: ops@simple-erp.local)"
    )
    TIMEOUT_SECONDS: ClassVar[float] = 10.0
    COUNTRY_CODES: ClassVar[Tuple[str, ...]] = ("fr",)
    RESPONSE_FORMAT: ClassVar[str] = "jsonv2"

    street: str = Field(description="Street line, including the number.")
    postal_code: str = Field(description="Postal code.")
    city: str = Field(description="City, town or village.")
    country: str = Field(
        default=DEFAULT_COUNTRY,
        description="Country name.",
    )
    latitude: Optional[float] = Field(
        default=None,
        description="Resolved latitude in decimal degrees, or None.",
    )
    longitude: Optional[float] = Field(
        default=None,
        description="Resolved longitude in decimal degrees, or None.",
    )
    geocoding_error: Optional[str] = Field(
        default=None,
        description="Stable code naming a non-fatal geocoding failure, or None.",
    )

    @field_validator("street", mode="before")
    def validate_street(cls, value: Optional[str]) -> str:
        """Validates that ``street`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``street`` value.

        Returns:
            str: The stripped street line.

        Raises:
            MTPostalAddressInvalidStreet: If ``value`` is not a string, or is
                empty once stripped.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTPostalAddressInvalidStreet(
                f"Invalid street: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("postal_code", mode="before")
    def validate_postal_code(cls, value: Optional[str]) -> str:
        """Validates that ``postal_code`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``postal_code`` value.

        Returns:
            str: The stripped postal code.

        Raises:
            MTPostalAddressInvalidPostalCode: If ``value`` is not a string, or
                is empty once stripped.

        Notes:
            The format is intentionally not constrained to five digits: the
            model must accept the postal codes of every country it may hold,
            and rejecting a valid foreign code is worse than accepting a
            malformed one that the geocoder will fail on anyway.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTPostalAddressInvalidPostalCode(
                f"Invalid postal_code: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("city", mode="before")
    def validate_city(cls, value: Optional[str]) -> str:
        """Validates that ``city`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``city`` value.

        Returns:
            str: The stripped city name.

        Raises:
            MTPostalAddressInvalidCity: If ``value`` is not a string, or is
                empty once stripped.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTPostalAddressInvalidCity(
                f"Invalid city: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("country", mode="before")
    def validate_country(cls, value: Optional[str]) -> str:
        """Validates that ``country`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``country`` value. ``None`` falls back
                to :attr:`DEFAULT_COUNTRY`.

        Returns:
            str: The stripped country name.

        Raises:
            MTPostalAddressInvalidCountry: If ``value`` is neither ``None`` nor
                a non-empty string.
        """
        if value is None:
            return cls.DEFAULT_COUNTRY
        if not isinstance(value, str) or not value.strip():
            raise MTPostalAddressInvalidCountry(
                f"Invalid country: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("latitude", mode="before")
    def validate_latitude(cls, value: Optional[Union[int, float]]) -> Optional[float]:  # noqa: E501
        """Validates that ``latitude`` is ``None`` or within ``-90..90``.

        Args:
            value (Optional[Union[int, float]]): Raw ``latitude`` value.

        Returns:
            Optional[float]: The validated latitude, or ``None``.

        Raises:
            MTPostalAddressInvalidLatitude: If ``value`` is neither ``None``
                nor a real number within ``-90..90``.
        """
        if value is None:
            return None
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise MTPostalAddressInvalidLatitude(
                f"Invalid latitude: {value!r}. Must be a number within -90..90 or None."
            )
        coerced = float(value)
        if not -90.0 <= coerced <= 90.0:
            raise MTPostalAddressInvalidLatitude(
                f"Invalid latitude: {coerced!r}. Must be within -90..90 or None."
            )
        return coerced

    @field_validator("longitude", mode="before")
    def validate_longitude(cls, value: Optional[Union[int, float]]) -> Optional[float]:  # noqa: E501
        """Validates that ``longitude`` is ``None`` or within ``-180..180``.

        Args:
            value (Optional[Union[int, float]]): Raw ``longitude`` value.

        Returns:
            Optional[float]: The validated longitude, or ``None``.

        Raises:
            MTPostalAddressInvalidLongitude: If ``value`` is neither ``None``
                nor a real number within ``-180..180``.
        """
        if value is None:
            return None
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise MTPostalAddressInvalidLongitude(
                f"Invalid longitude: {value!r}. "
                f"Must be a number within -180..180 or None."
            )
        coerced = float(value)
        if not -180.0 <= coerced <= 180.0:
            raise MTPostalAddressInvalidLongitude(
                f"Invalid longitude: {coerced!r}. Must be within -180..180 or None."
            )
        return coerced

    @field_validator("geocoding_error", mode="before")
    def validate_geocoding_error(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``geocoding_error`` is a known stable code.

        Args:
            value (Optional[str]): Raw ``geocoding_error`` value.

        Returns:
            Optional[str]: The validated code, or ``None``.

        Raises:
            MTPostalAddressInvalidGeocodingError: If ``value`` is not ``None``
                and not one of :attr:`VALID_GEOCODING_ERRORS`.
        """
        if value is None:
            return None
        if value not in cls.VALID_GEOCODING_ERRORS:
            raise MTPostalAddressInvalidGeocodingError(
                f"Invalid geocoding_error: {value!r}. Must be one of: "
                f"{', '.join(cls.VALID_GEOCODING_ERRORS)}, or None."
            )
        return value

    def model_post_init(self, context: JsonValue) -> None:  # noqa: ARG002
        """Resolve the address to a coordinate once it is built.

        Args:
            context (JsonValue): Pydantic's post-init context. Unused.

        Notes:
            - Runs after validation rather than as a validator, so the lookup
              sees the stripped, checked values it will send to the geocoder.
            - Skipped for an address that is already resolved, which is what
              makes re-hydrating a stored row free — see :meth:`_is_resolved`.
        """
        if self._is_resolved():
            return
        self._geocode()

    ############################
    # Internal Helpers Methods #
    ############################

    def _is_resolved(self) -> bool:
        """Return whether the address has already been through the geocoder.

        Returns:
            bool: ``True`` when both coordinates are set, or when a previous
            attempt recorded a ``geocoding_error``.

        Notes:
            The ``geocoding_error`` arm is what removes the need for a
            read-time kill switch. An address the geocoder could not place is
            stored with its code, and this class refuses to look it up again —
            without that, every read of an unplaceable address would retry the
            lookup, which is one blocking request per row on the exact rows
            that are guaranteed to fail again.

            A single coordinate is *not* resolved: half a point is unusable,
            and the lookup that would fill in the other half is worth making.
        """
        if self.geocoding_error is not None:
            return True
        return self.latitude is not None and self.longitude is not None

    def _geocode(self) -> None:
        """Look the address up and record the outcome on the instance.

        Notes:
            Never raises. Every failure becomes a stable ``geocoding_error``
            code: an address the service does not know must still be storable,
            or a customer could not be created from a new-build street the map
            has not caught up with. The missing coordinate resurfaces later as
            an unassignable planning requirement, which is a far better place
            to notice it than a failed creation.
        """
        logger = getLogger(__name__)
        logger.debug("Geocoding %s.", self.to_single_line())
        try:
            self._populate_from_payload(self._query_nominatim())
        except MTPostalAddressGeocodingFailed as exc:
            logger.error("Nominatim could not be reached: %s.", exc)
            self.geocoding_error = "service_unavailable"
        except MTPostalAddressNotFound as exc:
            logger.warning("Nominatim knows no matching address: %s.", exc)
            self.geocoding_error = "not_found"
        except MTPostalAddressInvalidResponse as exc:
            logger.error("Nominatim answered something unusable: %s.", exc)
            self.geocoding_error = "invalid_response"

    def _query_nominatim(self) -> Dict[str, JsonValue]:
        """Ask Nominatim for this address's coordinate.

        Returns:
            Dict[str, JsonValue]: The first candidate the service returned.

        Raises:
            MTPostalAddressGeocodingFailed: If the service could not be
                reached, timed out, or failed at the socket level.
            MTPostalAddressNotFound: If the service returned no candidate.
            MTPostalAddressInvalidResponse: If the answer is not readable JSON
                or does not have the documented shape.

        Notes:
            Nominatim's usage policy requires an identifying ``User-Agent``;
            a generic one gets the deployment's address blocked, which presents
            as every lookup failing for no visible reason.
        """
        parameters: Dict[str, Union[str, int]] = {
            "q": self.to_single_line(),
            "format": self.RESPONSE_FORMAT,
            "limit": 1,
            "addressdetails": 0,
        }
        if self.COUNTRY_CODES:
            parameters["countrycodes"] = ",".join(self.COUNTRY_CODES)
        request = Request(
            f"{self.GEOCODE_URL}?{urlencode(parameters)}",
            headers={"User-Agent": self.USER_AGENT},
        )
        try:
            with urlopen(request, timeout=self.TIMEOUT_SECONDS) as response:
                body = response.read()
        except (URLError, TimeoutError, OSError) as exc:
            raise MTPostalAddressGeocodingFailed(
                f"Geocoding request failed for {self.to_single_line()!r}: {exc}"
            ) from exc
        try:
            candidates = json.loads(body)
        except (json.JSONDecodeError, ValueError) as exc:
            raise MTPostalAddressInvalidResponse(
                f"Unreadable geocoding answer for {self.to_single_line()!r}: {exc}"
            ) from exc
        if not isinstance(candidates, list):
            raise MTPostalAddressInvalidResponse(
                f"Expected a list of candidates for {self.to_single_line()!r}, "
                f"got {type(candidates).__name__}."
            )
        if not candidates:
            raise MTPostalAddressNotFound(
                f"No geocoding candidate for {self.to_single_line()!r}."
            )
        first = candidates[0]
        if not isinstance(first, dict):
            raise MTPostalAddressInvalidResponse(
                f"Expected a candidate mapping for {self.to_single_line()!r}, "
                f"got {type(first).__name__}."
            )
        return first

    def _populate_from_payload(self, payload: Dict[str, JsonValue]) -> None:
        """Read the coordinate out of a candidate and store it.

        Args:
            payload (Dict[str, JsonValue]): The candidate to read.

        Raises:
            MTPostalAddressInvalidResponse: If the candidate carries no usable
                coordinate.

        Notes:
            - The coordinate arrives as **strings**, so both values are
              converted explicitly rather than trusted to be numbers.
            - Only the coordinate is taken. Nominatim also returns its own idea
              of the street, city and country, and overwriting the operator's
              input with them would silently rewrite an address someone typed
              deliberately — including the ones the geocoder matched loosely.
        """
        logger = getLogger(__name__)
        try:
            latitude = float(payload["lat"])
            longitude = float(payload["lon"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MTPostalAddressInvalidResponse(
                f"Candidate for {self.to_single_line()!r} carries no usable "
                f"coordinate: {exc}"
            ) from exc
        self.latitude = latitude
        self.longitude = longitude
        self.geocoding_error = None
        logger.info(
            "Resolved %s to (%s, %s).",
            self.to_single_line(),
            self.latitude,
            self.longitude,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    @classmethod
    def apply_geocoding_settings(
        cls,
        base_url: str,
        user_agent: str,
        timeout_seconds: float,
        country_codes: Tuple[str, ...],
    ) -> None:
        """Override the geocoding settings from the application configuration.

        Args:
            base_url (str): The Nominatim search endpoint.
            user_agent (str): Identifying User-Agent to send.
            timeout_seconds (float): Per-request timeout.
            country_codes (Tuple[str, ...]): Codes to restrict the search to.

        Notes:
            Called once from the application's start-up hook. The model cannot
            import the configuration — that would invert the dependency between
            the layers — so the values are pushed in instead of pulled.
        """
        logger = getLogger(__name__)
        cls.GEOCODE_URL = base_url
        cls.USER_AGENT = user_agent
        cls.TIMEOUT_SECONDS = timeout_seconds
        cls.COUNTRY_CODES = tuple(country_codes)
        logger.info(
            "Geocoding configured against %s, timeout %.1fs, countries %s.",
            base_url,
            timeout_seconds,
            ",".join(country_codes) if country_codes else "worldwide",
        )

    def is_geocoded(self) -> bool:
        """Return whether the address carries a usable coordinate.

        Returns:
            bool: ``True`` when both ``latitude`` and ``longitude`` are set.
        """
        return self.latitude is not None and self.longitude is not None

    def to_geo_point(self) -> Optional[GeoPoint]:
        """Return the address's coordinate as a :class:`GeoPoint`.

        Returns:
            Optional[GeoPoint]: The resolved point, or ``None`` when the
            address has not been geocoded.

        Notes:
            Returning ``None`` rather than raising lets the planning layer
            report an un-geocodable address as an unassignable requirement
            instead of failing the whole solve.
        """
        if self.latitude is None or self.longitude is None:
            return None
        return GeoPoint(latitude=self.latitude, longitude=self.longitude)

    def to_single_line(self) -> str:
        """Return the address formatted as one line.

        Returns:
            str: ``"<street>, <postal_code> <city>, <country>"``.

        Notes:
            This is the string handed to the geocoder, and the one displayed on
            a quote or an intervention.
        """
        return f"{self.street}, {self.postal_code} {self.city}, {self.country}"
