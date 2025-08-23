"""Config flow for Swiss Weather integration."""
from __future__ import annotations

import csv
from dataclasses import dataclass
import logging
from typing import Any

import requests
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util.location import distance

from .const import (
    CONF_POLLEN_STATION_CODE,
    CONF_POST_CODE,
    CONF_STATION_CODE,
    CONF_WEATHER_WARNINGS_NUMBER,
    DOMAIN,
)
from .pollen import PollenClient

STATION_LIST_URL = "https://data.geo.admin.ch/ch.meteoschweiz.messnetz-automatisch/ch.meteoschweiz.messnetz-automatisch_en.csv"

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA_BACKUP = vol.Schema(
    {
        vol.Required(CONF_POST_CODE): str,
        vol.Optional(CONF_STATION_CODE): str,
        vol.Optional(CONF_POLLEN_STATION_CODE): str,
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
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is None:
            try:
                station_options = await self._get_weather_station_options()
                pollen_station_options = await self._get_pollen_station_options()

                # Setup defaults if we're reconfiguring
                schema = vol.Schema({
                    vol.Required(CONF_POST_CODE): str,
                    vol.Optional(CONF_STATION_CODE): SelectSelector(
                        SelectSelectorConfig(
                            options=station_options,
                            mode=SelectSelectorMode.DROPDOWN
                        ),
                    ),
                    vol.Optional(CONF_POLLEN_STATION_CODE): SelectSelector(
                        SelectSelectorConfig(
                            options=pollen_station_options,
                            mode=SelectSelectorMode.DROPDOWN
                        )
                    ),
                    vol.Required(CONF_WEATHER_WARNINGS_NUMBER, default=1): NumberSelector(
                        NumberSelectorConfig(min=0, max=10, mode=NumberSelectorMode.BOX, step=1)
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
                    data_schema=STEP_USER_DATA_SCHEMA_BACKUP
                )

        _LOGGER.info("User chose %s", user_input)
        station_code = user_input.get(CONF_STATION_CODE) or "No Station"
        post_code = user_input.get(CONF_POST_CODE)
        pollen_station_code = user_input.get(CONF_POLLEN_STATION_CODE)
        return self.async_create_entry(title=f"Weather at {post_code} / {station_code or "No weather station"} / {pollen_station_code or "No pollen station"}", data=user_input,
            description=f"{user_input[CONF_POST_CODE]}")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the reconfigure step."""
        _LOGGER.info("Reconfigure with user dict %s", user_input)

        if user_input:
            self._abort_if_unique_id_mismatch()
            reconfigure_entry = self._get_reconfigure_entry()
            return self.async_update_reload_and_abort(
                reconfigure_entry, data_updates=user_input
            )

        station_options = await self._get_weather_station_options()
        pollen_station_options = await self._get_pollen_station_options()

        reconfigure_entry = self._get_reconfigure_entry()
        default_station_code = None
        default_pollen_station_code = None
        default_weather_alerts = 1
        if reconfigure_entry is not None:
            default_station_code = reconfigure_entry.data.get(CONF_STATION_CODE)
            default_pollen_station_code = reconfigure_entry.data.get(CONF_POLLEN_STATION_CODE)
            default_weather_alerts = reconfigure_entry.data.get(CONF_WEATHER_WARNINGS_NUMBER)
            if default_weather_alerts is None:
                default_weather_alerts = 1

        schema = vol.Schema({
            vol.Optional(CONF_STATION_CODE, default=default_station_code): SelectSelector(
                SelectSelectorConfig(
                    options=station_options,
                    mode=SelectSelectorMode.DROPDOWN
                ),
            ),
            vol.Optional(CONF_POLLEN_STATION_CODE, default=default_pollen_station_code): SelectSelector(
                SelectSelectorConfig(
                    options=pollen_station_options,
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Required(CONF_WEATHER_WARNINGS_NUMBER, default=default_weather_alerts): NumberSelector(
                NumberSelectorConfig(min=0, max=10, mode=NumberSelectorMode.BOX, step=1)
            )
        })
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema
        )

    def format_station_name_for_dropdown(self, station: WeatherStation) -> str:
        distance = self._get_distance_to_station(station)
        if distance is None:
            return f"{station.name} ({station.canton})"
        else:
            return f"{station.name} ({station.canton}) - {distance / 1000:.0f} km away"

    async def _get_weather_station_options(self):
        stations = await self.hass.async_add_executor_job(self.load_station_list)
        _LOGGER.debug("Stations received.", extra={"Stations": stations})
        if (self.hass.config.latitude is not None and
            self.hass.config.longitude is not None):
                stations = sorted(stations, key=lambda it: self._get_distance_to_station(it))
        return [SelectOptionDict(value=station.code,
                                    label=self.format_station_name_for_dropdown(station))
                                    for station in stations]

    async def _get_pollen_station_options(self):
        pollen_stations = await self.hass.async_add_executor_job(self.load_pollen_station_list)
        if (self.hass.config.latitude is not None and
            self.hass.config.longitude is not None):
                stations = sorted(pollen_stations, key=lambda it: self._get_distance_to_station(it))
        return [SelectOptionDict(value=station.code,
                                    label=self.format_station_name_for_dropdown(station))
                                    for station in stations]

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

    def load_pollen_station_list(self, encoding='ISO-8859-1') -> list[WeatherStation]:
        _LOGGER.info("Requesting pollen station list data...")
        pollen_client = PollenClient()
        pollen_station_list = pollen_client.get_pollen_station_list()
        if pollen_station_list is None:
            return []
        stations = []
        for station in pollen_station_list:
            _LOGGER.debug(station)
            stations.append(WeatherStation(
                station.name,
                station.abbreviation,
                int(station.altitude),
                station.lat,
                station.lng,
                station.canton
            ))
        return stations

def _int_or_none(val: str) -> int|None:
    if val is None:
        return None
    return int(val)

def _float_or_none(val: str) -> float|None:
    if val is None:
        return None
    return float(val)
