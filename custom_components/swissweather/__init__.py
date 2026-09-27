"""The Swiss Weather integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_POLLEN_STATION_CODE, DOMAIN
from .coordinator import SwissPollenDataCoordinator, SwissWeatherDataCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.WEATHER]

def get_weather_coordinator_key(entry: ConfigEntry):
    return entry.entry_id + "-weather-coordinator"

def get_pollen_coordinator_key(entry: ConfigEntry):
    return entry.entry_id + "-pollen-coordinator"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Swiss Weather from a config entry."""

    coordinator = SwissWeatherDataCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][get_weather_coordinator_key(entry)] = coordinator

    if entry.data.get(CONF_POLLEN_STATION_CODE):
        pollen_coordinator = SwissPollenDataCoordinator(hass, entry)
        await pollen_coordinator.async_config_entry_first_refresh()
        hass.data[DOMAIN][get_pollen_coordinator_key(entry)] = pollen_coordinator

    _LOGGER.debug("Bootstrapped entry %s", entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(get_weather_coordinator_key(entry), None)
        hass.data[DOMAIN].pop(get_pollen_coordinator_key(entry), None)
    return unload_ok
