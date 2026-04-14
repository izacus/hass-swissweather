"""Helpers to load and search MeteoSwiss local forecast points."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import logging

import requests

from .naming import format_station_display_name

_LOGGER = logging.getLogger(__name__)

FORECAST_POINT_LIST_URL = (
    "https://data.geo.admin.ch/ch.meteoschweiz.ogd-local-forecasting/"
    "ogd-local-forcasting_meta_point.csv"
)

SUPPORTED_FORECAST_POINT_TYPES = {"2", "3"}


@dataclass
class ForecastPoint:
    """Describes a local forecast point."""

    point_id: str
    point_type_id: str
    postal_code: str | None
    point_name: str
    point_type_en: str | None
    point_height_masl: int | None
    lat: float | None
    lng: float | None

    @property
    def display_name(self) -> str:
        return format_station_display_name(self.point_name) or self.point_name


def _int_or_none(value: str | None) -> int | None:
    if not value:
        return None
    return int(float(value))


def _float_or_none(value: str | None) -> float | None:
    if not value:
        return None
    return float(value)


def load_forecast_point_list(encoding: str = "latin-1") -> list[ForecastPoint]:
    """Load the list of MeteoSwiss local forecast points."""
    _LOGGER.info("Requesting forecast point list data...")
    with requests.get(FORECAST_POINT_LIST_URL, stream=True) as response:
        lines = (line.decode(encoding) for line in response.iter_lines())
        reader = csv.DictReader(lines, delimiter=";")
        points = []
        for row in reader:
            point_type_id = row.get("point_type_id")
            point_id = row.get("point_id")
            point_name = row.get("point_name")
            if (
                point_type_id not in SUPPORTED_FORECAST_POINT_TYPES
                or not point_id
                or not point_name
            ):
                continue

            points.append(
                ForecastPoint(
                    point_id=point_id,
                    point_type_id=point_type_id,
                    postal_code=row.get("postal_code") or None,
                    point_name=point_name,
                    point_type_en=row.get("point_type_en") or None,
                    point_height_masl=_int_or_none(row.get("point_height_masl")),
                    lat=_float_or_none(row.get("point_coordinates_wgs84_lat")),
                    lng=_float_or_none(row.get("point_coordinates_wgs84_lon")),
                )
            )
        _LOGGER.info("Retrieved %d forecast points.", len(points))
        return points


def find_forecast_point_by_id(
    points: list[ForecastPoint], point_id: str | None
) -> ForecastPoint | None:
    """Return the forecast point with the given point ID, if any."""
    if point_id is None:
        return None
    return next((point for point in points if point.point_id == str(point_id)), None)


def search_forecast_points(
    points: list[ForecastPoint], query: str
) -> list[ForecastPoint]:
    """Search forecast points using exact numeric or substring text matching."""
    normalized = query.strip()
    if not normalized:
        return []

    if normalized.isdigit():
        matches = [
            point
            for point in points
            if point.point_id == normalized or point.postal_code == normalized
        ]
        return sorted(matches, key=lambda point: (point.point_type_id, point.display_name))

    if len(normalized) < 2:
        return []

    lowered = normalized.casefold()
    matches = [
        point for point in points if lowered in point.display_name.casefold()
    ]
    return sorted(matches, key=lambda point: (point.display_name, point.point_type_id))


def format_forecast_point_label(point: ForecastPoint) -> str:
    """Build a user-facing label for a forecast point option."""
    if point.point_type_id == "2":
        postal_suffix = f" [PLZ {point.postal_code}]" if point.postal_code else " [PLZ]"
        return f"{point.display_name}{postal_suffix}"

    details = ["POI"]
    if point.point_height_masl is not None:
        details.append(f"{point.point_height_masl} m")
    details.append(f"id {point.point_id}")
    return f"{point.display_name} [{', '.join(details)}]"
