"""Config flow for Swiss Weather integration."""
from __future__ import annotations

import csv
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.data_entry_flow import section
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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
    CONF_GROUP_STATION_CODES,
    CONF_POLLEN_STATION_CODE,
    CONF_POST_CODE,
    CONF_STATION_CODE,
    CONF_WEATHER_WARNINGS_NUMBER,
    DOMAIN,
)
from .meteo import REQUEST_TIMEOUT, STATION_GROUP_FIELDS, CurrentWeather, MeteoClient
from .pollen import PollenClient

STATION_LIST_URL = "https://data.geo.admin.ch/ch.meteoschweiz.messnetz-automatisch/ch.meteoschweiz.messnetz-automatisch_en.csv"

_LOGGER = logging.getLogger(__name__)

GROUP_STATIONS_SECTION = "groupStations"
# Measurement in the station list a station needs to be offered for a group.
GROUP_MEASUREMENTS = {
    "temperature": "Temperature",
    "precipitation": "Precipitation",
    "wind": "Wind",
    "pressure": "Pressure",
    "sunshine": "Sunshine",
}

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
    measurements: list[str] = field(default_factory=list)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Swiss Weather."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            errors, placeholders = validate_main_station(user_input, await self.async_load_station_list())
        if user_input is None or errors:
            try:
                stations = await self.async_load_station_list()
                station_options = self._get_weather_station_options(stations, "Temperature", use_names=True)
                pollen_station_options = await self._get_pollen_station_options()

                # Setup defaults if we're reconfiguring
                schema = vol.Schema({
                    vol.Required(CONF_POST_CODE): str,
                    vol.Optional(CONF_STATION_CODE): SelectSelector(
                        SelectSelectorConfig(
                            options=station_options,
                            mode=SelectSelectorMode.DROPDOWN,
                            # Renders a searchable picker, see the group stations in the reconfigure step.
                            custom_value=True,
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
                    step_id="user", data_schema=self.add_suggested_values_to_schema(schema, user_input),
                    errors=errors, description_placeholders=placeholders
                )
            except Exception:
                _LOGGER.exception("Failed to retrieve station list, back to manual mode!")
                # If the API broke, we still give user the option to manually enter the
                # station code and continue.
                return self.async_show_form(
                    step_id="user",
                    data_schema=STEP_USER_DATA_SCHEMA_BACKUP
                )

        _LOGGER.info("User chose %s", user_input)
        station_code = user_input.get(CONF_STATION_CODE) or "No Station"
        post_code = user_input.get(CONF_POST_CODE)
        pollen_station_code = user_input.get(CONF_POLLEN_STATION_CODE)
        self._async_abort_entries_match({CONF_POST_CODE: post_code})
        return self.async_create_entry(title=f"Weather at {post_code} / {station_code or "No weather station"} / {pollen_station_code or "No pollen station"}", data=user_input,
            description=f"{user_input[CONF_POST_CODE]}")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the reconfigure step."""
        _LOGGER.info("Reconfigure with user dict %s", user_input)

        stations = await self.async_load_station_list()
        current_weather = await MeteoClient(async_get_clientsession(self.hass)).async_get_current_weather_for_all_stations()
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input:
            self._abort_if_unique_id_mismatch()
            reconfigure_entry = self._get_reconfigure_entry()
            data = merge_reconfigure_input(reconfigure_entry.data, user_input)
            errors, placeholders = validate_main_station(data, stations)
            if not errors:
                errors, placeholders = validate_group_stations(data, stations, current_weather)
            if not errors:
                return self.async_update_reload_and_abort(reconfigure_entry, data=data)

        station_options = self._get_weather_station_options(stations, "Temperature", use_names=True)
        pollen_station_options = await self._get_pollen_station_options()

        reconfigure_entry = self._get_reconfigure_entry()
        default_station_code = None
        default_pollen_station_code = None
        default_weather_alerts = 1
        entry_data = {}
        if reconfigure_entry is not None:
            # Show the rejected input again instead of the stored data.
            entry_data = data if errors else reconfigure_entry.data
            default_station_code = entry_data.get(CONF_STATION_CODE)
            default_pollen_station_code = entry_data.get(CONF_POLLEN_STATION_CODE)
            default_weather_alerts = entry_data.get(CONF_WEATHER_WARNINGS_NUMBER)
            if default_weather_alerts is None:
                default_weather_alerts = 1

        names_by_code = {station.code: station.name for station in stations}
        schema = vol.Schema({
            # suggested_value instead of default: a default of None fails validation when nothing is chosen.
            vol.Optional(CONF_STATION_CODE, description={"suggested_value": names_by_code.get(default_station_code, default_station_code)}): SelectSelector(
                SelectSelectorConfig(
                    options=station_options,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                ),
            ),
            vol.Optional(CONF_POLLEN_STATION_CODE, description={"suggested_value": default_pollen_station_code}): SelectSelector(
                SelectSelectorConfig(
                    options=pollen_station_options,
                    mode=SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Required(CONF_WEATHER_WARNINGS_NUMBER, default=default_weather_alerts): NumberSelector(
                NumberSelectorConfig(min=0, max=10, mode=NumberSelectorMode.BOX, step=1)
            ),
            # Cleared group pickers are missing from the input and remove the station.
            # The searchable picker shows the raw value instead of the label, so the options use
            # station names as values; they are turned back into codes when saving.
            vol.Required(GROUP_STATIONS_SECTION): section(
                vol.Schema({
                    vol.Optional(key, description={"suggested_value": names_by_code.get(entry_data.get(key), entry_data.get(key))}): SelectSelector(
                        SelectSelectorConfig(
                            options=self._get_weather_station_options(
                                get_reporting_stations(stations, current_weather, group), GROUP_MEASUREMENTS[group], use_names=True),
                            mode=SelectSelectorMode.DROPDOWN,
                            # Renders a searchable picker instead of a plain list.
                            custom_value=True,
                        )
                    )
                    for group, key in CONF_GROUP_STATION_CODES.items()
                }),
                {"collapsed": True},
            ),
        })
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors, description_placeholders=placeholders
        )

    def format_station_name_for_dropdown(self, station: WeatherStation) -> str:
        distance = self._get_distance_to_station(station)
        if distance is None:
            return f"{station.name} ({station.canton})"
        else:
            return f"{station.name} ({station.canton}) - {distance / 1000:.0f} km away"

    def _get_weather_station_options(self, stations: list[WeatherStation], measurement: str, use_names: bool = False) -> list[SelectOptionDict]:
        stations = [station for station in stations if measurement in station.measurements]
        if (self.hass.config.latitude is not None and
            self.hass.config.longitude is not None):
                stations = sorted(stations, key=lambda it: self._get_distance_to_station(it))
        return [SelectOptionDict(value=station.name if use_names else station.code,
                                    label=self.format_station_name_for_dropdown(station))
                                    for station in stations]

    async def _get_pollen_station_options(self) -> list[SelectOptionDict]:
        pollen_stations = await self.async_load_pollen_station_list()
        stations = pollen_stations
        if (self.hass.config.latitude is not None and
            self.hass.config.longitude is not None):
                stations = sorted(pollen_stations, key=lambda it: self._get_distance_to_station(it))
        return [SelectOptionDict(value=station.code,
                                    label=self.format_station_name_for_dropdown(station))
                                    for station in stations]

    def _get_distance_to_station(self, station: WeatherStation) -> float:
        INVALID_VALUE = 999000 # 1000km is larger than CH
        h_lat = self.hass.config.latitude
        h_lng = self.hass.config.longitude
        if h_lat is None or h_lng is None:
            return INVALID_VALUE
        d = distance(h_lat, h_lng, station.lat, station.lng)
        if d is None:
            return INVALID_VALUE
        return d

    async def async_load_station_list(self, encoding: str = 'ISO-8859-1') -> list[WeatherStation]:
        _LOGGER.info("Requesting station list data...")
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(STATION_LIST_URL, timeout=REQUEST_TIMEOUT) as r:
                text = await r.text(encoding=encoding)
                lines = text.splitlines()
                reader = csv.DictReader(lines, delimiter=';')
                stations = []
                for row in reader:
                    _LOGGER.debug(row)
                    code =  row.get("Abbr.")
                    if code is None:
                        _LOGGER.debug("No code in row.", extra={"Station": row})
                        continue
                    measurements = row.get("Measurements")
                    if measurements is None:
                        _LOGGER.debug("No measurements in row.", extra={"Station": row})
                        continue
                    # Only weather stations are part of the current measurements (VQHA80.csv).
                    if row.get("Station type") != "Weather station":
                        _LOGGER.debug("Skipping station without current data.", extra={"Station": row})
                        continue

                    stations.append(WeatherStation(row.get("Station"),
                                                   row.get("Abbr."),
                                                   _int_or_none(row.get("Station height m a. sea level")),
                                                   _float_or_none(row.get("Latitude")),
                                                   _float_or_none(row.get("Longitude")),
                                                   row.get("Canton"),
                                                   [m.strip() for m in measurements.split(",")]))
                _LOGGER.info("Retrieved %d stations.", len(stations))
                return stations
        except Exception:
            _LOGGER.exception("Failed to load station list")
            return []

    async def async_load_pollen_station_list(self) -> list[WeatherStation]:
        _LOGGER.info("Requesting pollen station list data...")
        session = async_get_clientsession(self.hass)
        pollen_client = PollenClient(session, self.hass.config.language)
        pollen_station_list = await pollen_client.async_get_pollen_station_list()
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

def get_reporting_stations(stations: list[WeatherStation], current_weather: list[CurrentWeather] | None,
                           group: str) -> list[WeatherStation]:
    """Return the stations currently reporting a value for the group, or all if current data is unavailable."""
    if current_weather is None:
        return stations
    reporting = {current.station for current in current_weather
                 if any(getattr(current, name)[0] is not None for name in STATION_GROUP_FIELDS[group])}
    return [station for station in stations if station.code in reporting]

def validate_main_station(data: dict[str, Any], stations: list[WeatherStation]) -> tuple[dict[str, str], dict[str, str]]:
    """Replace the chosen main station by its code."""
    value = data.get(CONF_STATION_CODE)
    # Without the station list, a typed code is kept as it is.
    if not value or not stations:
        return {}, {}
    code = find_station_code([station for station in stations if "Temperature" in station.measurements], value)
    if code is None:
        return {"base": "unknown_station"}, {"station": value}
    data[CONF_STATION_CODE] = code
    return {}, {}

def validate_group_stations(data: dict[str, Any], stations: list[WeatherStation],
                            current_weather: list[CurrentWeather] | None) -> tuple[dict[str, str], dict[str, str]]:
    """Replace chosen group stations by their codes and check they currently report values for their group."""
    selected = {group: key for group, key in CONF_GROUP_STATION_CODES.items() if data.get(key)}
    if not selected:
        return {}, {}
    if not stations or current_weather is None:
        return {"base": "cannot_connect"}, {}
    for key in selected.values():
        code = find_station_code(stations, data[key])
        if code is None:
            return {"base": "unknown_station"}, {"station": data[key]}
        data[key] = code
    for group, key in selected.items():
        if not any(station.code == data[key] for station in get_reporting_stations(stations, current_weather, group)):
            station_name = next(station.name for station in stations if station.code == data[key])
            return {"base": "no_group_values"}, {"station": station_name, "group": group}
    return {}, {}

def find_station_code(stations: list[WeatherStation], value: str) -> str | None:
    """Return the code of the station whose code or name matches value, ignoring case."""
    value = value.strip().casefold()
    return next((station.code for station in stations
                 if value in (station.code.casefold(), station.name.casefold())), None)

def merge_reconfigure_input(data: Mapping[str, Any], user_input: dict[str, Any]) -> dict[str, Any]:
    """Flatten the group stations section into the entry data, dropping cleared stations."""
    user_input = dict(user_input)
    group_input = user_input.pop(GROUP_STATIONS_SECTION, {})
    merged = {**data, **user_input}
    for key in CONF_GROUP_STATION_CODES.values():
        if group_input.get(key):
            merged[key] = group_input[key]
        else:
            merged.pop(key, None)
    return merged

def _int_or_none(val: str) -> int|None:
    if val is None:
        return None
    return int(val)

def _float_or_none(val: str) -> float|None:
    if val is None:
        return None
    return float(val)
