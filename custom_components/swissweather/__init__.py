"""The Swiss Weather integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_FORECAST_NAME,
    CONF_POLLEN_STATION_CODE,
    CONF_POLLEN_STATION_NAME,
    CONF_POST_CODE,
    CONF_STATION_CODE,
    CONF_STATION_NAME,
    DOMAIN,
)
from .coordinator import SwissPollenDataCoordinator, SwissWeatherDataCoordinator
from .naming import build_entry_title, format_station_display_name
from .station_lookup import (
    find_station_by_code,
    load_pollen_station_list,
    load_weather_station_list,
    split_place_and_canton,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.WEATHER]

def get_weather_coordinator_key(entry: ConfigEntry):
    return entry.entry_id + "-weather-coordinator"

def get_pollen_coordinator_key(entry: ConfigEntry):
    return entry.entry_id + "-pollen-coordinator"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Swiss Weather from a config entry."""
    entry = await _async_ensure_entry_names(hass, entry)

    coordinator = SwissWeatherDataCoordinator(hass, entry)
    pollen_coordinator = SwissPollenDataCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    await pollen_coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][get_weather_coordinator_key(entry)] = coordinator
    hass.data[DOMAIN][get_pollen_coordinator_key(entry)] = pollen_coordinator
    _LOGGER.debug("Bootstrapped entry %s", entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(get_weather_coordinator_key(entry))
        hass.data[DOMAIN].pop(get_pollen_coordinator_key(entry))
    return unload_ok


async def _async_ensure_entry_names(hass: HomeAssistant, entry: ConfigEntry) -> ConfigEntry:
    """Populate cached display names in older config entries and keep the title in sync."""
    data_updates = {}

    forecast_name = entry.data.get(CONF_FORECAST_NAME) or str(entry.data.get(CONF_POST_CODE, "")).strip()
    if forecast_name and entry.data.get(CONF_FORECAST_NAME) != forecast_name:
        data_updates[CONF_FORECAST_NAME] = forecast_name

    if entry.data.get(CONF_STATION_CODE) and not entry.data.get(CONF_STATION_NAME):
        weather_stations = await hass.async_add_executor_job(load_weather_station_list)
        station = find_station_by_code(weather_stations, entry.data.get(CONF_STATION_CODE))
        if station is not None:
            station_name, station_canton = split_place_and_canton(station.name)
            data_updates[CONF_STATION_NAME] = format_station_display_name(
                station_name, station_canton or station.canton, include_canton=True
            )

    if entry.data.get(CONF_POLLEN_STATION_CODE) and not entry.data.get(CONF_POLLEN_STATION_NAME):
        pollen_stations = await hass.async_add_executor_job(load_pollen_station_list)
        station = find_station_by_code(pollen_stations, entry.data.get(CONF_POLLEN_STATION_CODE))
        if station is not None:
            data_updates[CONF_POLLEN_STATION_NAME] = format_station_display_name(station.name)

    merged_data = {**entry.data, **data_updates}
    new_title = build_entry_title(
        merged_data.get(CONF_FORECAST_NAME),
        merged_data.get(CONF_STATION_NAME),
        merged_data.get(CONF_POLLEN_STATION_NAME),
    )

    if data_updates or entry.title != new_title:
        hass.config_entries.async_update_entry(entry, data=merged_data, title=new_title)

    return entry
