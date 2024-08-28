"""Config flow for Swiss Weather integration."""
from __future__ import annotations

import csv
from dataclasses import dataclass
import logging
from typing import Any

import requests
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util.location import distance

from .const import CONF_POST_CODE, CONF_STATION_CODE, DOMAIN

STATION_LIST_URL = "https://data.geo.admin.ch/ch.meteoschweiz.messnetz-automatisch/ch.meteoschweiz.messnetz-automatisch_en.csv"

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA_BACKUP = vol.Schema(
    {
        vol.Required(CONF_POST_CODE): str,
        vol.Optional(CONF_STATION_CODE): str,
    }
)

@dataclass
class WeatherStation:
    """Describes a single weather station as retrieved from the database."""

    name: str
    code: str
    altitude: int | None
    lat: float
    lng: float
    canton: str

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Swiss Weather."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            try:
                stations = await self.hass.async_add_executor_job(self.load_station_list)
                _LOGGER.debug("Stations received.", extra={"Stations": stations})
                if (self.hass.config.latitude is not None and
                    self.hass.config.longitude is not None):
                        stations = sorted(stations, key=lambda it: self._get_distance_to_station(it))
                options = [SelectOptionDict(value=station.code,
                                            label=self.format_station_name_for_dropdown(station))
                                            for station in stations]
                schema = vol.Schema({
                    vol.Required(CONF_POST_CODE): str,
                    vol.Optional(CONF_STATION_CODE): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.DROPDOWN
                        )
                    )
                })
                return self.async_show_form(
                    step_id="user", data_schema=schema
                )
            except Exception:
                _LOGGER.exception("Failed to retrieve station list, back to manual mode!")
                # If the API broke, we still give user the option to manually enter the
                # station code and continue.
                return self.async_show_form(
                    step_id="user", data_schema=STEP_USER_DATA_SCHEMA_BACKUP
                )

        _LOGGER.info("User chose %s", user_input)
        station_code = user_input.get(CONF_STATION_CODE) or "No Station"
        return self.async_create_entry(title="Swiss Weather", data=user_input,
            description=f"{user_input[CONF_POST_CODE]} / {station_code}")

    def format_station_name_for_dropdown(self, station: WeatherStation) -> str:
        distance = self._get_distance_to_station(station)
        if distance is None:
            return f"{station.name} ({station.canton})"
        else:
            return f"{station.name} ({station.canton}) - {distance / 1000:.0f} km away"

    def _get_distance_to_station(self, station: WeatherStation):
        h_lat = self.hass.config.latitude
        h_lng = self.hass.config.longitude
        if h_lat is None or h_lng is None:
            return None
        return distance(h_lat, h_lng, station.lat, station.lng)

    def load_station_list(self, encoding='ISO-8859-1') -> list[WeatherStation]:
        _LOGGER.info("Requesting station list data...")
        with requests.get(STATION_LIST_URL, stream = True) as r:
            lines = (line.decode(encoding) for line in r.iter_lines())
            reader = csv.DictReader(lines, delimiter=';')
            stations = []
            for row in reader:
                _LOGGER.debug(row)
                code =  row.get("Abbr.")
                if code is None:
                    _LOGGER.debug("No code in row.", extra={"Station": row})
                    continue
                # Skip stations that have almost no useable data
                measurements = row.get("Measurements")
                if measurements is None:
                    _LOGGER.debug("No measurements in row.", extra={"Station": row})
                    continue
                if "Temperature" not in measurements:
                    _LOGGER.debug("Skipping station due to lack of data.", extra={"Station": row})
                    continue

                stations.append(WeatherStation(row.get("Station"),
                                               row.get("Abbr."),
                                               _int_or_none(row.get("Station height m a. sea level")),
                                               _float_or_none(row.get("Latitude")),
                                               _float_or_none(row.get("Longitude")),
                                               row.get("Canton")))
            _LOGGER.info("Retrieved %d stations.", len(stations))
            return stations

def _int_or_none(val: str) -> int|None:
    if val is None:
        return None
    return int(val)

def _float_or_none(val: str) -> float|None:
    if val is None:
        return None
    return float(val)
