from __future__ import annotations

# Standard library imports
from typing import Any, Dict, List, Self

# Third-party imports
import pytest

from models.geo import postal_address as postal_address_module

# First-party imports
from models.geo.exceptions import (
    MTInvalidPostalAddressException,
    MTPostalAddressInvalidCity,
    MTPostalAddressInvalidCountry,
    MTPostalAddressInvalidGeocodingError,
    MTPostalAddressInvalidLatitude,
    MTPostalAddressInvalidLongitude,
    MTPostalAddressInvalidPostalCode,
    MTPostalAddressInvalidStreet,
)
from models.geo.geo_point import GeoPoint
from models.geo.postal_address import PostalAddress


class _FakeResponse:
    """A stand-in for the object ``urlopen`` returns."""

    def __init__(self, body: bytes) -> None:
        """Store the body the fake response will yield.

        Args:
            body (bytes): The payload ``read`` returns.
        """
        self.body = body

    def read(self) -> bytes:
        """Return the payload.

        Returns:
            bytes: The stored body.
        """
        return self.body

    def __enter__(self) -> Self:
        """Enter the context manager.

        Returns:
            Self: This response.
        """
        return self

    def __exit__(self, *exc_info: object) -> bool:
        """Leave the context manager.

        Args:
            *exc_info (Any): The exception triple, if any.

        Returns:
            bool: ``False``, so any exception propagates.
        """
        return False


def _explode(*args: Any, **kwargs: Any) -> None:
    """Fail loudly if a lookup is attempted.

    Args:
        *args (Any): Ignored.
        **kwargs (Any): Ignored.

    Raises:
        AssertionError: Always.
    """
    raise AssertionError("No geocoding request was expected here.")


@pytest.fixture
def valid_address_kwargs() -> Dict[str, Any]:
    """Return the minimal keyword arguments for a valid address.

    Returns:
        Dict[str, Any]: Constructor keyword arguments.
    """
    return {
        "street": "12 rue de Rivoli",
        "postal_code": "75004",
        "city": "Paris",
    }


class TestPostalAddress:
    """Tests for the PostalAddress model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_minimal_valid_construction(
        self, valid_address_kwargs: Dict[str, Any]
    ) -> None:
        """An address needs only a street, a postal code and a city."""
        address = PostalAddress(**valid_address_kwargs)
        assert address.street == "12 rue de Rivoli"
        assert address.postal_code == "75004"
        assert address.city == "Paris"

    def test_country_defaults_to_france(
        self, valid_address_kwargs: Dict[str, Any]
    ) -> None:
        """An omitted country falls back to the configured default."""
        assert PostalAddress(**valid_address_kwargs).country == "France"

    def test_coordinates_default_to_unset(
        self, valid_address_kwargs: Dict[str, Any]
    ) -> None:
        """A fresh address carries no coordinate and no error."""
        address = PostalAddress(**valid_address_kwargs)
        assert address.latitude is None
        assert address.longitude is None
        assert address.geocoding_error is None

    def test_construction_is_inert_while_geocoding_is_suppressed(
        self, valid_address_kwargs: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The kill switch stops the lookup entirely.

        Notes:
            The suite runs with geocoding suppressed by an autouse fixture, so
            this also proves that safeguard actually holds: without it every
            test that builds an address would call out.
        """
        monkeypatch.setattr(postal_address_module, "urlopen", _explode)
        address = PostalAddress(**valid_address_kwargs)
        assert address.latitude is None
        assert address.geocoding_error is None

    @pytest.mark.parametrize(
        ("field", "raw", "expected"),
        [
            pytest.param(
                "street", "  12 rue de Rivoli  ", "12 rue de Rivoli", id="street"
            ),
            pytest.param("postal_code", " 75004 ", "75004", id="postal_code"),
            pytest.param("city", "  Paris ", "Paris", id="city"),
            pytest.param("country", " Belgium ", "Belgium", id="country"),
        ],
    )
    def test_text_fields_are_stripped(
        self,
        valid_address_kwargs: Dict[str, Any],
        field: str,
        raw: str,
        expected: str,
    ) -> None:
        """Surrounding whitespace is removed from every text field."""
        address = PostalAddress(**{**valid_address_kwargs, field: raw})
        assert getattr(address, field) == expected

    # ------------------------------------------------------------------ #
    #  street / postal_code / city validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(42, id="Invalid - int"),
            pytest.param([], id="Invalid - list"),
        ],
    )
    def test_invalid_street_raises(
        self, valid_address_kwargs: Dict[str, Any], invalid_value: Any
    ) -> None:
        """A street that is not a non-empty string is rejected."""
        with pytest.raises(MTPostalAddressInvalidStreet):
            PostalAddress(**{**valid_address_kwargs, "street": invalid_value})

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("  ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(75004, id="Invalid - int"),
        ],
    )
    def test_invalid_postal_code_raises(
        self, valid_address_kwargs: Dict[str, Any], invalid_value: Any
    ) -> None:
        """A postal code that is not a non-empty string is rejected."""
        with pytest.raises(MTPostalAddressInvalidPostalCode):
            PostalAddress(**{**valid_address_kwargs, "postal_code": invalid_value})

    def test_foreign_postal_codes_are_accepted(
        self, valid_address_kwargs: Dict[str, Any]
    ) -> None:
        """The format is not constrained to five digits.

        Notes:
            Rejecting a valid foreign code would be worse than accepting a
            malformed one, which the geocoder will fail on anyway.
        """
        address = PostalAddress(
            **{**valid_address_kwargs, "postal_code": "SW1A 1AA", "country": "UK"}
        )
        assert address.postal_code == "SW1A 1AA"

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(3.14, id="Invalid - float"),
        ],
    )
    def test_invalid_city_raises(
        self, valid_address_kwargs: Dict[str, Any], invalid_value: Any
    ) -> None:
        """A city that is not a non-empty string is rejected."""
        with pytest.raises(MTPostalAddressInvalidCity):
            PostalAddress(**{**valid_address_kwargs, "city": invalid_value})

    # ------------------------------------------------------------------ #
    #  country validation
    # ------------------------------------------------------------------ #

    def test_none_country_falls_back_to_the_default(
        self, valid_address_kwargs: Dict[str, Any]
    ) -> None:
        """An explicit None country yields the default rather than an error."""
        address = PostalAddress(**{**valid_address_kwargs, "country": None})
        assert address.country == "France"

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(33, id="Invalid - int"),
        ],
    )
    def test_invalid_country_raises(
        self, valid_address_kwargs: Dict[str, Any], invalid_value: Any
    ) -> None:
        """A country that is neither None nor a non-empty string is rejected."""
        with pytest.raises(MTPostalAddressInvalidCountry):
            PostalAddress(**{**valid_address_kwargs, "country": invalid_value})

    # ------------------------------------------------------------------ #
    #  latitude / longitude validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param(90.1, id="Invalid - above range"),
            pytest.param(-90.1, id="Invalid - below range"),
            pytest.param("48.8", id="Invalid - string"),
            pytest.param(True, id="Invalid - bool"),
        ],
    )
    def test_invalid_latitude_raises(
        self, valid_address_kwargs: Dict[str, Any], invalid_value: Any
    ) -> None:
        """A latitude outside -90..90, or not a number, is rejected."""
        with pytest.raises(MTPostalAddressInvalidLatitude):
            PostalAddress(**{**valid_address_kwargs, "latitude": invalid_value})

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param(180.1, id="Invalid - above range"),
            pytest.param(-180.1, id="Invalid - below range"),
            pytest.param("2.35", id="Invalid - string"),
            pytest.param(False, id="Invalid - bool"),
        ],
    )
    def test_invalid_longitude_raises(
        self, valid_address_kwargs: Dict[str, Any], invalid_value: Any
    ) -> None:
        """A longitude outside -180..180, or not a number, is rejected."""
        with pytest.raises(MTPostalAddressInvalidLongitude):
            PostalAddress(**{**valid_address_kwargs, "longitude": invalid_value})

    def test_none_coordinates_are_accepted(
        self, valid_address_kwargs: Dict[str, Any]
    ) -> None:
        """An ungeocoded address holds None for both coordinates."""
        address = PostalAddress(
            **{**valid_address_kwargs, "latitude": None, "longitude": None}
        )
        assert address.latitude is None
        assert address.longitude is None

    # ------------------------------------------------------------------ #
    #  geocoding_error validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "code", ["service_unavailable", "not_found", "invalid_response"]
    )
    def test_known_geocoding_errors_are_accepted(
        self, valid_address_kwargs: Dict[str, Any], code: str
    ) -> None:
        """Each documented stable error code is accepted."""
        address = PostalAddress(**{**valid_address_kwargs, "geocoding_error": code})
        assert address.geocoding_error == code

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("boom", id="Invalid - unknown code"),
            pytest.param("SERVICE_UNAVAILABLE", id="Invalid - wrong case"),
            pytest.param(500, id="Invalid - int"),
        ],
    )
    def test_invalid_geocoding_error_raises(
        self, valid_address_kwargs: Dict[str, Any], invalid_value: Any
    ) -> None:
        """An unknown geocoding-error code is rejected."""
        with pytest.raises(MTPostalAddressInvalidGeocodingError):
            PostalAddress(**{**valid_address_kwargs, "geocoding_error": invalid_value})

    # ------------------------------------------------------------------ #
    #  is_geocoded / to_geo_point / to_single_line
    # ------------------------------------------------------------------ #

    def test_is_geocoded_is_false_without_coordinates(
        self, valid_address_kwargs: Dict[str, Any]
    ) -> None:
        """An address with no coordinate is not geocoded."""
        assert PostalAddress(**valid_address_kwargs).is_geocoded() is False

    def test_is_geocoded_is_true_with_both_coordinates(
        self, valid_address_kwargs: Dict[str, Any]
    ) -> None:
        """An address with both coordinates is geocoded."""
        address = PostalAddress(
            **{**valid_address_kwargs, "latitude": 48.8566, "longitude": 2.3522}
        )
        assert address.is_geocoded() is True

    @pytest.mark.parametrize(
        ("latitude", "longitude"),
        [
            pytest.param(48.8566, None, id="latitude only"),
            pytest.param(None, 2.3522, id="longitude only"),
        ],
    )
    def test_a_half_geocoded_address_is_not_geocoded(
        self,
        valid_address_kwargs: Dict[str, Any],
        latitude: Any,
        longitude: Any,
    ) -> None:
        """One coordinate alone is unusable, so it does not count."""
        address = PostalAddress(
            **{**valid_address_kwargs, "latitude": latitude, "longitude": longitude}
        )
        assert address.is_geocoded() is False
        assert address.to_geo_point() is None

    def test_to_geo_point_returns_the_coordinate(
        self, valid_address_kwargs: Dict[str, Any]
    ) -> None:
        """A geocoded address converts to the solver's coordinate type."""
        address = PostalAddress(
            **{**valid_address_kwargs, "latitude": 48.8566, "longitude": 2.3522}
        )
        assert address.to_geo_point() == GeoPoint(latitude=48.8566, longitude=2.3522)

    def test_to_geo_point_returns_none_when_ungeocoded(
        self, valid_address_kwargs: Dict[str, Any]
    ) -> None:
        """An ungeocoded address yields None rather than raising.

        Notes:
            This is what lets the planning layer report an un-geocodable
            address as an unassignable requirement instead of failing the
            whole solve.
        """
        assert PostalAddress(**valid_address_kwargs).to_geo_point() is None

    def test_to_single_line(self, valid_address_kwargs: Dict[str, Any]) -> None:
        """The one-line form is what is geocoded and displayed."""
        address = PostalAddress(**valid_address_kwargs)
        assert address.to_single_line() == "12 rue de Rivoli, 75004 Paris, France"

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTPostalAddressInvalidCity,
            MTPostalAddressInvalidCountry,
            MTPostalAddressInvalidGeocodingError,
            MTPostalAddressInvalidLatitude,
            MTPostalAddressInvalidLongitude,
            MTPostalAddressInvalidPostalCode,
            MTPostalAddressInvalidStreet,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidPostalAddressException."""
        assert issubclass(exception_class, MTInvalidPostalAddressException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_model_dump_round_trip(self, valid_address_kwargs: Dict[str, Any]) -> None:
        """An address serialises to a dict and rebuilds identically."""
        address = PostalAddress(
            **{**valid_address_kwargs, "latitude": 48.8566, "longitude": 2.3522}
        )
        assert PostalAddress(**address.model_dump()) == address

    def test_class_constants_are_not_fields(
        self, valid_address_kwargs: Dict[str, Any]
    ) -> None:
        """ClassVars stay out of the serialised payload."""
        dumped = PostalAddress(**valid_address_kwargs).model_dump()
        assert "VALID_GEOCODING_ERRORS" not in dumped
        assert "DEFAULT_COUNTRY" not in dumped


@pytest.mark.geocoding
class TestPostalAddressGeocoding:
    """Tests for the Nominatim lookup performed when an address is built.

    Notes:
        The class carries the ``geocoding`` marker, which opts every test in it
        out of the autouse fixture that neutralises the lookup. The transport
        is stubbed instead, so the real resolution path runs without a socket
        being opened.
    """

    # ------------------------------------------------------------------ #
    #  Successful resolution
    # ------------------------------------------------------------------ #

    def test_construction_resolves_the_coordinate(
        self, valid_address_kwargs: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Building an address fills in its latitude and longitude."""
        monkeypatch.setattr(
            postal_address_module,
            "urlopen",
            lambda request, timeout=0: _FakeResponse(
                b'[{"lat": "48.8566", "lon": "2.3522"}]'
            ),
        )
        address = PostalAddress(**valid_address_kwargs)
        assert address.latitude == pytest.approx(48.8566)
        assert address.longitude == pytest.approx(2.3522)
        assert address.geocoding_error is None
        assert address.is_geocoded() is True

    def test_the_request_identifies_the_deployment(
        self, valid_address_kwargs: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nominatim's usage policy requires an identifying User-Agent.

        Notes:
            A generic or absent User-Agent gets the deployment's address
            blocked, which presents as every lookup silently failing.
        """
        captured: List[Any] = []

        def _capture(request: Any, timeout: float = 0) -> Any:
            captured.append(request)
            return _FakeResponse(b'[{"lat": "48.8", "lon": "2.3"}]')

        monkeypatch.setattr(postal_address_module, "urlopen", _capture)
        PostalAddress(**valid_address_kwargs)
        user_agent = captured[0].get_header("User-agent")
        assert user_agent
        assert "simple-erp" in user_agent

    def test_the_query_carries_the_full_address(
        self, valid_address_kwargs: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The one-line form is what gets searched."""
        captured: List[Any] = []

        def _capture(request: Any, timeout: float = 0) -> Any:
            captured.append(request.full_url)
            return _FakeResponse(b'[{"lat": "48.8", "lon": "2.3"}]')

        monkeypatch.setattr(postal_address_module, "urlopen", _capture)
        PostalAddress(**valid_address_kwargs)
        assert "75004" in captured[0]
        assert "Rivoli" in captured[0]

    def test_the_operators_own_fields_are_not_overwritten(
        self, valid_address_kwargs: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only the coordinate is taken from the answer.

        Notes:
            Nominatim returns its own idea of the street, city and country.
            Writing those back would silently rewrite an address someone typed
            deliberately, including the ones it matched only loosely.
        """
        monkeypatch.setattr(
            postal_address_module,
            "urlopen",
            lambda request, timeout=0: _FakeResponse(
                b'[{"lat": "48.8", "lon": "2.3", "address": {"city": "Lyon", '
                b'"country": "Belgium"}}]'
            ),
        )
        address = PostalAddress(**valid_address_kwargs)
        assert address.city == "Paris"
        assert address.country == "France"

    # ------------------------------------------------------------------ #
    #  Re-resolution is avoided
    # ------------------------------------------------------------------ #

    def test_an_already_resolved_address_is_not_looked_up(
        self, valid_address_kwargs: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A supplied coordinate is trusted rather than re-checked.

        Notes:
            This is what keeps re-hydrating a stored row free, and it stops a
            coordinate an operator corrected by hand from being overwritten.
        """
        monkeypatch.setattr(postal_address_module, "urlopen", _explode)
        address = PostalAddress(
            **{**valid_address_kwargs, "latitude": 1.0, "longitude": 2.0}
        )
        assert address.latitude == 1.0

    @pytest.mark.parametrize(
        "stored_error",
        [
            pytest.param("not_found", id="not_found"),
            pytest.param("service_unavailable", id="service_unavailable"),
            pytest.param("invalid_response", id="invalid_response"),
        ],
    )
    def test_a_stored_failure_is_not_retried(
        self,
        valid_address_kwargs: Dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        stored_error: str,
    ) -> None:
        """An address that already failed carries its code and stays put.

        Notes:
            This is what makes a read free without a kill switch. The rows the
            geocoder could not place are exactly the ones a "no coordinate,
            look it up" rule would retry on every read — one blocking request
            per row, inside an async handler, for a lookup that just failed.

            Retrying is deliberate: clear the code and rebuild the address.
        """
        monkeypatch.setattr(postal_address_module, "urlopen", _explode)
        address = PostalAddress(
            **{**valid_address_kwargs, "geocoding_error": stored_error}
        )
        assert address.geocoding_error == stored_error
        assert address.latitude is None

    def test_clearing_the_code_makes_the_address_resolvable_again(
        self, valid_address_kwargs: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rebuilding without the stored code retries the lookup."""
        monkeypatch.setattr(
            postal_address_module,
            "urlopen",
            lambda request, timeout=0: _FakeResponse(
                b'[{"lat": "48.8566", "lon": "2.3522"}]'
            ),
        )
        failed = PostalAddress(
            **{**valid_address_kwargs, "geocoding_error": "not_found"}
        )
        retried = PostalAddress(**{**failed.model_dump(), "geocoding_error": None})
        assert retried.latitude == pytest.approx(48.8566)
        assert retried.geocoding_error is None

    def test_a_half_resolved_address_is_looked_up(
        self, valid_address_kwargs: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One coordinate alone is unusable, so the lookup still runs."""
        monkeypatch.setattr(
            postal_address_module,
            "urlopen",
            lambda request, timeout=0: _FakeResponse(
                b'[{"lat": "48.8566", "lon": "2.3522"}]'
            ),
        )
        address = PostalAddress(
            **{**valid_address_kwargs, "latitude": 1.0, "longitude": None}
        )
        assert address.longitude == pytest.approx(2.3522)

    # ------------------------------------------------------------------ #
    #  Failures become stable codes, never exceptions
    # ------------------------------------------------------------------ #

    def test_an_unreachable_service_records_a_code(
        self, valid_address_kwargs: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A network failure must not stop a customer being created."""

        def _fail(request: Any, timeout: float = 0) -> Any:
            raise postal_address_module.URLError("connection refused")

        monkeypatch.setattr(postal_address_module, "urlopen", _fail)
        address = PostalAddress(**valid_address_kwargs)
        assert address.geocoding_error == "service_unavailable"
        assert address.is_geocoded() is False

    def test_a_timeout_records_a_code(
        self, valid_address_kwargs: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A slow service is recorded, not raised."""

        def _timeout(request: Any, timeout: float = 0) -> Any:
            raise TimeoutError("timed out")

        monkeypatch.setattr(postal_address_module, "urlopen", _timeout)
        address = PostalAddress(**valid_address_kwargs)
        assert address.geocoding_error == "service_unavailable"

    def test_an_unknown_address_records_not_found(
        self, valid_address_kwargs: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An address the map does not know is still storable.

        Notes:
            A new-build street the map has not caught up with must not block
            creating the customer who lives on it.
        """
        monkeypatch.setattr(
            postal_address_module,
            "urlopen",
            lambda request, timeout=0: _FakeResponse(b"[]"),
        )
        address = PostalAddress(**valid_address_kwargs)
        assert address.geocoding_error == "not_found"

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param(b"not json", id="Invalid - not JSON"),
            pytest.param(b'{"lat": "48.8"}', id="Invalid - not a list"),
            pytest.param(b'["a string"]', id="Invalid - candidate not a mapping"),
            pytest.param(b'[{"lon": "2.3"}]', id="Invalid - no latitude"),
            pytest.param(
                b'[{"lat": "north", "lon": "2.3"}]', id="Invalid - not a number"
            ),
        ],
    )
    def test_an_unusable_answer_records_invalid_response(
        self,
        valid_address_kwargs: Dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        body: bytes,
    ) -> None:
        """A malformed answer is recorded rather than raised."""
        monkeypatch.setattr(
            postal_address_module,
            "urlopen",
            lambda request, timeout=0: _FakeResponse(body),
        )
        address = PostalAddress(**valid_address_kwargs)
        assert address.geocoding_error == "invalid_response"

    def test_the_geocoding_exceptions_never_escape(
        self, valid_address_kwargs: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The typed failures are internal: construction always succeeds.

        Notes:
            They exist so the resolver can tell the three outcomes apart
            without inspecting the transport's own exception types, not so a
            caller has to handle them.
        """

        def _fail(request: Any, timeout: float = 0) -> Any:
            raise postal_address_module.URLError("connection refused")

        monkeypatch.setattr(postal_address_module, "urlopen", _fail)
        assert PostalAddress(**valid_address_kwargs).street == "12 rue de Rivoli"

    # ------------------------------------------------------------------ #
    #  Settings applied from configuration
    # ------------------------------------------------------------------ #

    def test_settings_can_be_applied_from_configuration(self) -> None:
        """The application pushes its configured settings into the model.

        Notes:
            Pushed rather than pulled: a model importing the configuration
            would invert the dependency between the layers.
        """
        original = (
            PostalAddress.GEOCODE_URL,
            PostalAddress.USER_AGENT,
            PostalAddress.TIMEOUT_SECONDS,
            PostalAddress.COUNTRY_CODES,
        )
        try:
            PostalAddress.apply_geocoding_settings(
                base_url="https://nominatim.internal/search",
                user_agent="simple-erp-test/1.0",
                timeout_seconds=2.0,
                country_codes=("be",),
            )
            assert PostalAddress.GEOCODE_URL == "https://nominatim.internal/search"
            assert PostalAddress.COUNTRY_CODES == ("be",)
        finally:
            (
                PostalAddress.GEOCODE_URL,
                PostalAddress.USER_AGENT,
                PostalAddress.TIMEOUT_SECONDS,
                PostalAddress.COUNTRY_CODES,
            ) = original
