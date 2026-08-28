import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import logging

import requests

from .meteo import FloatValue, StationInfo

logger = logging.getLogger(__name__)

POLLEN_STATIONS_URL = 'https://data.geo.admin.ch/ch.meteoschweiz.ogd-pollen/ogd-pollen_meta_stations.csv'
POLLEN_DATA_URL = 'https://data.geo.admin.ch/ch.meteoschweiz.ogd-pollen/{station}/ogd-pollen_{station}_h_now.csv'
HTTP_TIMEOUT_SECONDS = 15
POLLEN_COLUMNS = {
    "birch": "kabetuh0",
    "grasses": "khpoach0",
    "alder": "kaalnuh0",
    "hazel": "kacoryh0",
    "beech": "kafaguh0",
    "ash": "kafraxh0",
    "oak": "kaquerh0",
}

class PollenLevel(StrEnum):
    """ Marks pollen level """
    NONE = "None"
    LOW = "Low"
    MEDIUM = "Medium"
    STRONG = "Strong"
    VERY_STRONG = "Very Strong"

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

    def get_pollen_station_list(self) -> list[StationInfo] | None:
        station_list = self._get_csv_dictionary_for_url(POLLEN_STATIONS_URL, encoding='latin-1')
        logger.debug("Loading %s", POLLEN_STATIONS_URL)
        if station_list is None:
            return None
        stations = []
        for row in station_list:
            stations.append(StationInfo(row.get('station_name'),
                                  row.get('station_abbr'),
                                  row.get('station_type_en'),
                                  to_float(row.get('station_height_masl')),
                                  to_float(row.get('station_coordinates_wgs84_lat')),
                                  to_float(row.get('station_coordinates_wgs84_lon')),
                                  row.get('station_canton')))
        if len(stations) == 0:
            logger.warning("Couldn't find any stations in the dataset!")
            return None
        logger.info("Found %d stations for pollen.", len(stations))
        return stations

    def get_current_pollen_for_station(self, stationAbbrev: str) -> CurrentPollen | None:
        station = stationAbbrev.lower()
        url = POLLEN_DATA_URL.format(station=station)
        logger.debug("Loading %s", url)

        try:
            response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.exceptions.RequestException:
            logger.error("Connection failure.", exc_info=True)
            return None

        rows = list(
            csv.DictReader(
                response.content.decode("latin-1").splitlines(), delimiter=";"
            )
        )
        if not rows:
            logger.warning("No pollen data found for %s", stationAbbrev)
            return None

        latest_row = rows[-1]
        timestamp_raw = latest_row.get("reference_timestamp")
        timestamp = None
        if timestamp_raw:
            timestamp = datetime.strptime(
                timestamp_raw, "%d.%m.%Y %H:%M"
            ).replace(tzinfo=UTC)

        unit = "p/m³"
        values = {
            key: to_float(latest_row.get(column))
            for key, column in POLLEN_COLUMNS.items()
        }
        if all(value is None for value in values.values()):
            return None

        return CurrentPollen(
            stationAbbrev,
            timestamp,
            (values["birch"], unit),
            (values["grasses"], unit),
            (values["alder"], unit),
            (values["hazel"], unit),
            (values["beech"], unit),
            (values["ash"], unit),
            (values["oak"], unit),
        )

    def _get_csv_dictionary_for_url(self, url, encoding='utf-8'):
        try:
            logger.debug("Requesting station data from %s...", url)
            with requests.get(url, stream = True) as r:
                lines = (line.decode(encoding) for line in r.iter_lines())
                yield from csv.DictReader(lines, delimiter=';')
        except requests.exceptions.RequestException:
            logger.error("Connection failure.", exc_info=True)
            return None
