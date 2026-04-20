"""Helpers to load and search MeteoSwiss local forecast points."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import logging
import unicodedata

from aiohttp import ClientError, ClientSession

from .naming import format_station_display_name
from .request import REQUEST_TIMEOUT, async_get_with_retry

_LOGGER = logging.getLogger(__name__)

FORECAST_POINT_LIST_URL = (
    "https://data.geo.admin.ch/ch.meteoschweiz.ogd-local-forecasting/"
    "ogd-local-forecasting_meta_point.csv"
)

SUPPORTED_FORECAST_POINT_TYPES = {"2", "3"}


class ForecastPointMetadataLoadError(Exception):
    """Raised when forecast point metadata cannot be loaded reliably."""


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


def _search_aliases(value: str | None) -> set[str]:
    """Build normalized aliases for robust place matching."""
    if not value:
        return set()

    lowered = value.strip().casefold()
    if not lowered:
        return set()

    aliases = {lowered}
    german_normalized = (
        lowered.replace("?", "ae")
        .replace("?", "oe")
        .replace("?", "ue")
        .replace("?", "ss")
    )
    aliases.add(german_normalized)

    ascii_aliases = set()
    for alias in aliases:
        normalized = unicodedata.normalize("NFKD", alias)
        ascii_alias = "".join(
            char for char in normalized if not unicodedata.combining(char)
        )
        ascii_aliases.add(ascii_alias)

    aliases.update(ascii_aliases)
    return {alias for alias in aliases if alias}


async def async_load_forecast_point_list(
    session: ClientSession,
    encoding: str = "latin-1",
    *,
    raise_on_error: bool = False,
) -> list[ForecastPoint]:
    """Load the list of MeteoSwiss local forecast points."""
    _LOGGER.info("Requesting forecast point list data...")
    try:
        async def _parse_csv(response) -> list[ForecastPoint]:
            text = await response.text(encoding=encoding)
            lines = text.splitlines()
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
            return points

        points = await async_get_with_retry(
            session,
            FORECAST_POINT_LIST_URL,
            logger=_LOGGER,
            response_handler=_parse_csv,
            timeout=REQUEST_TIMEOUT,
        )
    except (
        ClientError,
        TimeoutError,
        UnicodeDecodeError,
        csv.Error,
        ValueError,
    ) as err:
        _LOGGER.warning(
            "Failed to load MeteoSwiss forecast point metadata", exc_info=True
        )
        if raise_on_error:
            raise ForecastPointMetadataLoadError(
                "Failed to load MeteoSwiss forecast point metadata"
            ) from err
        return []

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

    query_aliases = _search_aliases(normalized)
    matches = [
        point
        for point in points
        if any(
            query_alias in point_alias
            for query_alias in query_aliases
            for point_alias in _search_aliases(point.display_name)
        )
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
