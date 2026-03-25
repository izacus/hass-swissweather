"""Config flow for Swiss Weather integration."""
from __future__ import annotations

import logging
from typing import Any

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
    CONF_FORECAST_NAME,
    CONF_POLLEN_STATION_CODE,
    CONF_POLLEN_STATION_NAME,
    CONF_POST_CODE,
    CONF_STATION_CODE,
    CONF_STATION_NAME,
    CONF_WEATHER_WARNINGS_NUMBER,
    DOMAIN,
)
from .naming import build_entry_title, format_station_display_name
from .station_lookup import (
    WeatherStation,
    find_station_by_code,
    load_pollen_station_list,
    load_weather_station_list,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA_BACKUP = vol.Schema(
    {
        vol.Required(CONF_POST_CODE): str,
        vol.Optional(CONF_STATION_CODE): str,
        vol.Optional(CONF_POLLEN_STATION_CODE): str,
    }
)

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
        resolved_data = await self._augment_entry_data(user_input)
        return self.async_create_entry(
            title=build_entry_title(
                resolved_data.get(CONF_FORECAST_NAME),
                resolved_data.get(CONF_STATION_NAME),
                resolved_data.get(CONF_POLLEN_STATION_NAME),
            ),
            data=resolved_data,
            description=f"{resolved_data[CONF_POST_CODE]}",
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the reconfigure step."""
        _LOGGER.info("Reconfigure with user dict %s", user_input)

        if user_input:
            self._abort_if_unique_id_mismatch()
            reconfigure_entry = self._get_reconfigure_entry()
            resolved_data = await self._augment_entry_data(user_input)
            return self.async_update_reload_and_abort(
                reconfigure_entry, data_updates=resolved_data
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
        stations = await self.hass.async_add_executor_job(load_weather_station_list)
        _LOGGER.debug("Stations received.", extra={"Stations": stations})
        if (self.hass.config.latitude is not None and
            self.hass.config.longitude is not None):
                stations = sorted(stations, key=lambda it: self._get_distance_to_station(it))
        return [SelectOptionDict(value=station.code,
                                    label=self.format_station_name_for_dropdown(station))
                                    for station in stations]

    async def _get_pollen_station_options(self):
        pollen_stations = await self.hass.async_add_executor_job(load_pollen_station_list)
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

    async def _augment_entry_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        """Attach resolved display names to the config entry data."""
        resolved_data = dict(user_input)
        post_code = user_input.get(CONF_POST_CODE)
        if post_code is None:
            reconfigure_entry = self._get_reconfigure_entry()
            if reconfigure_entry is not None:
                post_code = reconfigure_entry.data.get(CONF_POST_CODE)
        resolved_data[CONF_POST_CODE] = post_code
        resolved_data[CONF_FORECAST_NAME] = str(post_code).strip()

        weather_stations = await self.hass.async_add_executor_job(load_weather_station_list)
        pollen_stations = await self.hass.async_add_executor_job(load_pollen_station_list)

        station = find_station_by_code(weather_stations, user_input.get(CONF_STATION_CODE))
        pollen_station = find_station_by_code(pollen_stations, user_input.get(CONF_POLLEN_STATION_CODE))

        resolved_data[CONF_STATION_NAME] = (
            format_station_display_name(station.name, station.canton, include_canton=True)
            if station is not None
            else None
        )
        resolved_data[CONF_POLLEN_STATION_NAME] = (
            format_station_display_name(pollen_station.name)
            if pollen_station is not None
            else None
        )
        return resolved_data
