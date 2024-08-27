"""The Swiss Weather integration."""
from __future__ import annotations

from datetime import timedelta
import datetime
import logging
from random import randrange
from typing import Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_POST_CODE, CONF_STATION_CODE, DOMAIN
from .meteo import CurrentState, CurrentWeather, MeteoClient, WeatherForecast

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.WEATHER]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Swiss Weather from a config entry."""

    coordinator = SwissWeatherDataCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

class SwissWeatherDataCoordinator(DataUpdateCoordinator["SwissWeatherCoordinator"]):
    """Swiss weather data coordinator"""

    _client : MeteoClient = None

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self._station_code = config_entry.data.get(CONF_STATION_CODE)
        self._post_code = config_entry.data[CONF_POST_CODE]
        self._client = MeteoClient()
        update_interval = timedelta(minutes=randrange(55, 65))
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval,
                         always_update=False)

    async def _async_update_data(self) -> Tuple[CurrentState, WeatherForecast]:
        _LOGGER.info("Updating weather data...")
        if self._station_code is None:
            current_state = None
        else:
            try:
                current_state = await self.hass.async_add_executor_job(
                    self._client.get_current_weather_for_station, self._station_code)
                _LOGGER.debug(f"Current state: {current_state}")
            except Exception as e:
                _LOGGER.exception(e)
                current_state = None

        try:
            current_forecast = await self.hass.async_add_executor_job(self._client.get_forecast, self._post_code)
            _LOGGER.debug(f"Current forecast: {current_forecast}")
            if current_state is None:
                current = current_forecast.current
                noValue = (None, None)
                current_state = CurrentWeather(None, datetime.datetime.now(tz=datetime.UTC), current.currentTemperature, noValue, noValue, noValue, noValue, noValue, noValue, noValue, noValue, noValue, noValue, noValue)
        except Exception as e:
            _LOGGER.exception(e)
            raise UpdateFailed(f"Update failed: {e}") from e
        return (current_state, current_forecast)