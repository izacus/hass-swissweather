import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import logging

import requests

from .meteo import FORECAST_USER_AGENT, FloatValue, StationInfo

logger = logging.getLogger(__name__)

POLLEN_STATIONS_URL = 'https://data.geo.admin.ch/ch.meteoschweiz.ogd-pollen/ogd-pollen_meta_stations.csv'
POLLEN_DATA_URL = 'https://www.meteoschweiz.admin.ch/product/output/measured-values/stationsTable/messwerte-pollen-{}-1h/stationsTable.messwerte-pollen-{}-1h.en.json'

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
        timestamp = None
        unit = "p/m³"
        types = ["birke", "graeser", "erle", "hasel", "buche", "esche", "eiche"]
        values = []
        for t in types:
            value, ts = self.get_current_pollen_for_station_type(stationAbbrev, t)
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

    def get_current_pollen_for_station_type(self, stationAbbrev: str, pollenKey: str) -> (float|None, datetime|None):
        url = POLLEN_DATA_URL.format(pollenKey, pollenKey)
        logger.debug("Loading %s", url)
        try:
            pollenJson = requests.get(url, headers =
                                        { "User-Agent": FORECAST_USER_AGENT,
                                        "Accept": "application/json" }).json()
            stations = pollenJson.get("stations")
            if stations is None:
                return (None, None)
            for station in stations:
                if station.get("id") is None or station.get("id").lower() != stationAbbrev.lower():
                    continue
                current = station.get("current")
                if current is None:
                    logger.warning("No current data for %s in dataset for %s!", stationAbbrev, pollenKey)
                    continue
                timestamp_val = current.get("date")
                if timestamp_val is not None:
                    timestamp = datetime.fromtimestamp(timestamp_val / 1000, UTC)
                else:
                    timestamp = None
                value = to_float(current.get("value"))
                return (value, timestamp)
            logger.warning("Couldn't find %s in dataset for %s!", stationAbbrev, pollenKey)
            return (None, None)
        except requests.exceptions.RequestException as _:
            logger.error("Connection failure.", exc_info=True)
            return (None, None)

    def _get_csv_dictionary_for_url(self, url, encoding='utf-8'):
        try:
            logger.debug("Requesting station data from %s...", url)
            with requests.get(url, stream = True) as r:
                lines = (line.decode(encoding) for line in r.iter_lines())
                yield from csv.DictReader(lines, delimiter=';')
        except requests.exceptions.RequestException:
            logger.error("Connection failure.", exc_info=True)
            return None
