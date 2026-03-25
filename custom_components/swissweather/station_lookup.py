"""Helpers to load and resolve station metadata."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import logging

import requests

from .pollen import PollenClient

_LOGGER = logging.getLogger(__name__)

STATION_LIST_URL = "https://data.geo.admin.ch/ch.meteoschweiz.messnetz-automatisch/ch.meteoschweiz.messnetz-automatisch_en.csv"


@dataclass
class WeatherStation:
    """Describes a single weather or pollen station."""

    name: str
    code: str
    altitude: int | None
    lat: float
    lng: float
    canton: str


def _int_or_none(val: str) -> int | None:
    if val is None:
        return None
    return int(val)


def _float_or_none(val: str) -> float | None:
    if val is None:
        return None
    return float(val)


def load_weather_station_list(encoding: str = "ISO-8859-1") -> list[WeatherStation]:
    """Load the list of MeteoSwiss weather stations."""
    _LOGGER.info("Requesting station list data...")
    with requests.get(STATION_LIST_URL, stream=True) as response:
        lines = (line.decode(encoding) for line in response.iter_lines())
        reader = csv.DictReader(lines, delimiter=";")
        stations = []
        for row in reader:
            code = row.get("Abbr.")
            measurements = row.get("Measurements")
            if code is None or measurements is None or "Temperature" not in measurements:
                continue

            stations.append(
                WeatherStation(
                    row.get("Station"),
                    code,
                    _int_or_none(row.get("Station height m a. sea level")),
                    _float_or_none(row.get("Latitude")),
                    _float_or_none(row.get("Longitude")),
                    row.get("Canton"),
                )
            )
        _LOGGER.info("Retrieved %d weather stations.", len(stations))
        return stations


def load_pollen_station_list() -> list[WeatherStation]:
    """Load the list of pollen stations."""
    _LOGGER.info("Requesting pollen station list data...")
    pollen_client = PollenClient()
    pollen_station_list = pollen_client.get_pollen_station_list()
    if pollen_station_list is None:
        return []

    stations = []
    for station in pollen_station_list:
        stations.append(
            WeatherStation(
                station.name,
                station.abbreviation,
                int(station.altitude),
                station.lat,
                station.lng,
                station.canton,
            )
        )
    return stations


def find_station_by_code(stations: list[WeatherStation], code: str | None) -> WeatherStation | None:
    """Return the station with the given code, if any."""
    if code is None:
        return None
    return next((station for station in stations if station.code == code), None)
