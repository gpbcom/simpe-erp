from __future__ import annotations

# Standard library imports

# Third-party imports
import pytest

# First-party imports
from models.geo.exceptions import (
    MTGeoPointInvalidLatitude,
    MTGeoPointInvalidLongitude,
    MTInvalidGeoPointException,
)
from models.geo.geo_point import GeoPoint
from tests.annotations import ModelInput


class TestGeoPoint:
    """Tests for the GeoPoint model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_minimal_valid_construction(self) -> None:
        """A point is built from a latitude and a longitude."""
        point = GeoPoint(latitude=48.8566, longitude=2.3522)
        assert point.latitude == 48.8566
        assert point.longitude == 2.3522

    def test_integer_coordinates_are_coerced_to_float(self) -> None:
        """Integer coordinates are accepted and stored as floats."""
        point = GeoPoint(latitude=48, longitude=2)
        assert isinstance(point.latitude, float)
        assert isinstance(point.longitude, float)

    @pytest.mark.parametrize(
        ("latitude", "longitude"),
        [
            pytest.param(90.0, 180.0, id="upper bounds"),
            pytest.param(-90.0, -180.0, id="lower bounds"),
            pytest.param(0.0, 0.0, id="null island"),
        ],
    )
    def test_extreme_but_valid_coordinates(
        self, latitude: float, longitude: float
    ) -> None:
        """The range bounds are inclusive."""
        point = GeoPoint(latitude=latitude, longitude=longitude)
        assert point.latitude == latitude
        assert point.longitude == longitude

    # ------------------------------------------------------------------ #
    #  latitude validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_latitude",
        [
            pytest.param(90.1, id="Invalid - above range"),
            pytest.param(-90.1, id="Invalid - below range"),
            pytest.param("48.8", id="Invalid - string"),
            pytest.param(None, id="Invalid - None"),
            pytest.param([48.8], id="Invalid - list"),
            pytest.param(True, id="Invalid - bool"),
        ],
    )
    def test_invalid_latitude_raises(self, invalid_latitude: ModelInput) -> None:
        """A latitude outside -90..90, or not a number, is rejected."""
        with pytest.raises(MTGeoPointInvalidLatitude):
            GeoPoint(latitude=invalid_latitude, longitude=2.3522)

    # ------------------------------------------------------------------ #
    #  longitude validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_longitude",
        [
            pytest.param(180.1, id="Invalid - above range"),
            pytest.param(-180.1, id="Invalid - below range"),
            pytest.param("2.35", id="Invalid - string"),
            pytest.param(None, id="Invalid - None"),
            pytest.param({}, id="Invalid - dict"),
            pytest.param(False, id="Invalid - bool"),
        ],
    )
    def test_invalid_longitude_raises(self, invalid_longitude: ModelInput) -> None:
        """A longitude outside -180..180, or not a number, is rejected."""
        with pytest.raises(MTGeoPointInvalidLongitude):
            GeoPoint(latitude=48.8566, longitude=invalid_longitude)

    # ------------------------------------------------------------------ #
    #  distance_km
    # ------------------------------------------------------------------ #

    def test_distance_to_itself_is_zero(self) -> None:
        """A point is zero kilometres from itself."""
        point = GeoPoint(latitude=48.8566, longitude=2.3522)
        assert point.distance_km(point) == pytest.approx(0.0, abs=1e-9)

    def test_distance_is_symmetric(self) -> None:
        """The distance does not depend on which end is the origin."""
        paris = GeoPoint(latitude=48.8566, longitude=2.3522)
        lyon = GeoPoint(latitude=45.7640, longitude=4.8357)
        assert paris.distance_km(lyon) == pytest.approx(lyon.distance_km(paris))

    def test_distance_paris_to_lyon_is_about_392_km(self) -> None:
        """A known city pair lands within 1% of the published distance."""
        paris = GeoPoint(latitude=48.8566, longitude=2.3522)
        lyon = GeoPoint(latitude=45.7640, longitude=4.8357)
        assert paris.distance_km(lyon) == pytest.approx(392.0, rel=0.01)

    def test_one_degree_of_latitude_is_about_111_km(self) -> None:
        """A degree of latitude is roughly 111 km anywhere on the globe."""
        origin = GeoPoint(latitude=0.0, longitude=0.0)
        north = GeoPoint(latitude=1.0, longitude=0.0)
        assert origin.distance_km(north) == pytest.approx(111.2, rel=0.01)

    def test_antipodal_points_are_half_the_circumference_apart(self) -> None:
        """Antipodes sit half a great circle apart. The arcsin never overflows."""
        origin = GeoPoint(latitude=0.0, longitude=0.0)
        antipode = GeoPoint(latitude=0.0, longitude=180.0)
        assert origin.distance_km(antipode) == pytest.approx(20015.0, rel=0.01)

    def test_distance_across_the_antimeridian_is_short(self) -> None:
        """Two points either side of the date line are close, not a world apart."""
        west = GeoPoint(latitude=0.0, longitude=179.9)
        east = GeoPoint(latitude=0.0, longitude=-179.9)
        assert west.distance_km(east) < 30.0

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [MTGeoPointInvalidLatitude, MTGeoPointInvalidLongitude],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidGeoPointException."""
        assert issubclass(exception_class, MTInvalidGeoPointException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_model_dump_round_trip(self) -> None:
        """A point serialises to a plain dict and rebuilds identically."""
        point = GeoPoint(latitude=48.8566, longitude=2.3522)
        dumped = point.model_dump()
        assert dumped == {"latitude": 48.8566, "longitude": 2.3522}
        assert GeoPoint(**dumped) == point

    def test_earth_radius_is_not_a_field(self) -> None:
        """The Earth radius is a ClassVar, so it never reaches the payload."""
        assert (
            "EARTH_RADIUS_KM" not in GeoPoint(latitude=0.0, longitude=0.0).model_dump()
        )
