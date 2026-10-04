import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import logging

import aiohttp

from .meteo import (
    DEFAULT_LANGUAGE,
    FORECAST_USER_AGENT,
    REQUEST_TIMEOUT,
    FloatValue,
    StationInfo,
    to_meteoswiss_language,
)

logger = logging.getLogger(__name__)

POLLEN_STATIONS_URL = 'https://data.geo.admin.ch/ch.meteoschweiz.ogd-pollen/ogd-pollen_meta_stations.csv'
POLLEN_DATA_URL = 'https://www.meteoschweiz.admin.ch/product/output/measured-values/stationsTable/messwerte-pollen-{key}-1h/stationsTable.messwerte-pollen-{key}-1h.{language}.json'

class PollenLevel(StrEnum):
    """ Marks pollen level """
    NONE = "None"
    LOW = "Low"
    MEDIUM = "Medium"
    STRONG = "Strong"
    VERY_STRONG = "Very Strong"

# Plant-specific load thresholds (low, medium, strong) based on official MeteoSwiss classification:
# https://www.meteoswiss.admin.ch/dam/jcr:43b4f361-8bc1-4af7-a232-c126de0f2f80/Belastungsklassen-der-allergenen-Pollenarten_E.pdf
_POLLEN_THRESHOLDS: dict[str, tuple[int, int, int]] = {
    "birch":   (10,  70, 300),
    "grasses": (20,  50, 150),
    "alder":   (10,  70, 250),
    "hazel":   (10,  70, 250),
    "beech":   (50, 130, 400),
    "ash":     (10, 100, 350),
    "oak":     (50, 130, 400),
}
_DEFAULT_POLLEN_THRESHOLDS = (10, 70, 250)

def get_pollen_level(value: float | None, plant_key: str) -> PollenLevel | None:
    """Return the pollen load level for a given value and plant type."""
    if value is None:
        return None
    if value <= 0:
        return PollenLevel.NONE
    low, medium, strong = _POLLEN_THRESHOLDS.get(plant_key, _DEFAULT_POLLEN_THRESHOLDS)
    if value <= low:
        return PollenLevel.LOW
    if value <= medium:
        return PollenLevel.MEDIUM
    if value <= strong:
        return PollenLevel.STRONG
    return PollenLevel.VERY_STRONG

@dataclass
class CurrentPollen:
    stationAbbr: str
    timestamp: datetime
    birch: FloatValue
    grasses: FloatValue
    alder: FloatValue
    hazel: FloatValue
    beech: FloatValue
    ash: FloatValue
    oak: FloatValue

def to_float(string: str) -> float | None:
    if string is None:
        return None

    try:
        return float(string)
    except ValueError:
        return None

class PollenClient:
    """Returns values for pollen."""

    session: aiohttp.ClientSession
    language: str = DEFAULT_LANGUAGE

    """
    Initializes the client.

    Languages available are en, de, fr and it. Any other tag (including full
    Home Assistant tags such as "de-CH") is normalized to one of those.
    """
    def __init__(self, session: aiohttp.ClientSession, language: str | None = DEFAULT_LANGUAGE) -> None:
        self.session = session
        self.language = to_meteoswiss_language(language)

    async def async_get_pollen_station_list(self) -> list[StationInfo] | None:
        station_list = await self._async_get_csv_rows_for_url(POLLEN_STATIONS_URL, encoding='latin-1')
        logger.debug("Loading %s", POLLEN_STATIONS_URL)
        if station_list is None:
            return None
        stations = []
        for row in station_list:
            if not isinstance(row, dict):
                continue
            name = row.get('station_name')
            abbr = row.get('station_abbr')
            if not name or not abbr:
                continue
            stations.append(StationInfo(name,
                                  abbr,
                                  row.get(f'station_type_{self.language}'),
                                  to_float(row.get('station_height_masl')),
                                  to_float(row.get('station_coordinates_wgs84_lat')),
                                  to_float(row.get('station_coordinates_wgs84_lon')),
                                  row.get('station_canton')))
        if len(stations) == 0:
            logger.warning("Couldn't find any stations in the dataset!")
            return None
        logger.info("Found %d stations for pollen.", len(stations))
        return stations

    async def async_get_current_pollen_for_station(self, stationAbbrev: str) -> CurrentPollen | None:
        timestamp = None
        unit = "p/m³"
        types = ["birke", "graeser", "erle", "hasel", "buche", "esche", "eiche"]
        values = []
        for t in types:
            value, ts = await self.async_get_current_pollen_for_station_type(stationAbbrev, t)
            if timestamp is None and ts is not None:
                timestamp = ts
            values.append(value)
        if all(v is None for v in values):
            return None

        return CurrentPollen(
            stationAbbrev,
            timestamp,
            (values[0], unit),
            (values[1], unit),
            (values[2], unit),
            (values[3], unit),
            (values[4], unit),
            (values[5], unit),
            (values[6], unit)
        )

    async def async_get_current_pollen_for_station_type(self, stationAbbrev: str, pollenKey: str) -> tuple[float|None, datetime|None]:
        url = POLLEN_DATA_URL.format(key=pollenKey, language=self.language)
        logger.debug("Loading %s", url)
        try:
            async with self.session.get(
                url,
                headers={
                    "User-Agent": FORECAST_USER_AGENT,
                    "Accept": "application/json"
                },
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status != 200:
                    logger.warning("Failed to load %s: HTTP %s", url, response.status)
                    return (None, None)
                pollenJson = await response.json()
                if not isinstance(pollenJson, dict):
                    return (None, None)
                stations = pollenJson.get("stations")
                if not isinstance(stations, list):
                    return (None, None)
                for station in stations:
                    if not isinstance(station, dict):
                        continue
                    station_id = station.get("id")
                    if not station_id or not isinstance(station_id, str) or station_id.lower() != stationAbbrev.lower():
                        continue
                    current = station.get("current")
                    if not isinstance(current, dict):
                        logger.warning("No current data for %s in dataset for %s!", stationAbbrev, pollenKey)
                        continue
                    timestamp_val = current.get("date")
                    if timestamp_val is None:
                        logger.warning("No timestamp for %s in dataset for %s!", stationAbbrev, pollenKey)
                        continue
                    try:
                        timestamp = datetime.fromtimestamp(float(timestamp_val) / 1000, UTC)
                    except (ValueError, TypeError, OSError):
                        logger.warning("Failed to parse date %s for %s!", timestamp_val, stationAbbrev)
                        continue
                    value = to_float(current.get("value"))
                    return (value, timestamp)
                logger.warning("Couldn't find %s in dataset for %s!", stationAbbrev, pollenKey)
                return (None, None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as _:
            logger.error("Connection failure or malformed JSON.", exc_info=True)
            return (None, None)

    async def _async_get_csv_rows_for_url(self, url: str, encoding: str = 'utf-8') -> list[dict[str, str]] | None:
        try:
            logger.debug("Requesting station data from %s...", url)
            async with self.session.get(url, timeout=REQUEST_TIMEOUT) as r:
                if r.status != 200:
                    logger.warning("Failed to load %s: HTTP %s", url, r.status)
                    return None
                text = await r.text(encoding=encoding)
                return list(csv.DictReader(text.splitlines(), delimiter=';'))
        except (aiohttp.ClientError, TimeoutError):
            logger.error("Connection failure.", exc_info=True)
            return None
