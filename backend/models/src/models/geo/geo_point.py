from __future__ import annotations

# Standard library imports
import math
from typing import ClassVar, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.geo.exceptions import (
    MTGeoPointInvalidLatitude,
    MTGeoPointInvalidLongitude,
)


class GeoPoint(BaseModel):
    """A resolved geographic coordinate, in decimal degrees.

    Attributes:
        EARTH_RADIUS_KM (ClassVar[float]): Mean Earth radius used by the
            great-circle distance, in kilometres.
        latitude (float): Latitude in decimal degrees, within ``-90..90``.
        longitude (float): Longitude in decimal degrees, within ``-180..180``.

    Notes:
        This is the coordinate type the planning solver works with. It is
        deliberately narrower than :class:`~models.geo.postal_address.PostalAddress`:
        by the time a location reaches the solver it must already be resolved,
        so both components are required and the "not geocoded yet" state cannot
        be represented here at all.
    """

    EARTH_RADIUS_KM: ClassVar[float] = 6371.0088

    latitude: float = Field(
        description="Latitude in decimal degrees, within -90..90.",
    )
    longitude: float = Field(
        description="Longitude in decimal degrees, within -180..180.",
    )

    @field_validator("latitude", mode="before")
    def validate_latitude(cls, value: Union[int, float]) -> float:
        """Validates that ``latitude`` is a real number within ``-90..90``.

        Args:
            value (Union[int, float]): Raw ``latitude`` value.

        Returns:
            float: The validated latitude as a float.

        Raises:
            MTGeoPointInvalidLatitude: If ``value`` is not a real number or
                falls outside the ``-90..90`` range.
        """
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise MTGeoPointInvalidLatitude(
                f"Invalid latitude: {value!r}. Must be a number within -90..90."
            )
        coerced = float(value)
        if not -90.0 <= coerced <= 90.0:
            raise MTGeoPointInvalidLatitude(
                f"Invalid latitude: {coerced!r}. Must be within -90..90."
            )
        return coerced

    @field_validator("longitude", mode="before")
    def validate_longitude(cls, value: Union[int, float]) -> float:
        """Validates that ``longitude`` is a real number within ``-180..180``.

        Args:
            value (Union[int, float]): Raw ``longitude`` value.

        Returns:
            float: The validated longitude as a float.

        Raises:
            MTGeoPointInvalidLongitude: If ``value`` is not a real number or
                falls outside the ``-180..180`` range.
        """
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise MTGeoPointInvalidLongitude(
                f"Invalid longitude: {value!r}. Must be a number within -180..180."
            )
        coerced = float(value)
        if not -180.0 <= coerced <= 180.0:
            raise MTGeoPointInvalidLongitude(
                f"Invalid longitude: {coerced!r}. Must be within -180..180."
            )
        return coerced

    ############################
    # Publicly Exposed Methods #
    ############################

    def distance_km(self, other: GeoPoint) -> float:
        """Return the great-circle distance to another point, in kilometres.

        Args:
            other (GeoPoint): The destination point.

        Returns:
            float: The haversine distance in kilometres. ``0.0`` when both
            points are identical.

        Notes:
            This is a straight-line distance over the sphere, not a road
            distance. The planning layer converts it into a duration through a
            configurable average speed; swapping in real road distances is a
            matter of replacing the travel-time provider, not this method.
        """
        origin_latitude = math.radians(self.latitude)
        destination_latitude = math.radians(other.latitude)
        delta_latitude = math.radians(other.latitude - self.latitude)
        delta_longitude = math.radians(other.longitude - self.longitude)
        squared_half_chord = (
            math.sin(delta_latitude / 2) ** 2
            + math.cos(origin_latitude)
            * math.cos(destination_latitude)
            * math.sin(delta_longitude / 2) ** 2
        )
        central_angle = 2 * math.asin(min(1.0, math.sqrt(squared_half_chord)))
        return self.EARTH_RADIUS_KM * central_angle
