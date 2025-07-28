"""Coordinates updates for weather data."""

import datetime
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_POLLEN_STATION_CODE, CONF_POST_CODE, CONF_STATION_CODE, DOMAIN
from .meteo import (
    CurrentWeather,
    MeteoClient,
    Warning,
    WarningLevel,
    WarningType,
    WeatherForecast,
)
from .pollen import CurrentPollen, PollenClient

_LOGGER = logging.getLogger(__name__)

class SwissWeatherDataCoordinator(DataUpdateCoordinator[tuple[CurrentWeather | None, WeatherForecast | None]]):
    """Coordinates data loads for all sensors."""

    _client : MeteoClient

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self._station_code = config_entry.data.get(CONF_STATION_CODE)
        self._post_code = config_entry.data[CONF_POST_CODE]
        self._client = MeteoClient()
        update_interval = timedelta(minutes=10)
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval,
                         always_update=False)

    async def _async_update_data(self) -> tuple[CurrentWeather | None, WeatherForecast | None]:
        if self._station_code is None:
            _LOGGER.warning("Station code not set, not loading current state.")
            current_state = None
        else:
            _LOGGER.info("Loading current weather state for %s", self._station_code)
            try:
                current_state = await self.hass.async_add_executor_job(
                    self._client.get_current_weather_for_station, self._station_code)
                _LOGGER.debug("Current state: %s", current_state)
            except Exception as e:
                _LOGGER.exception(e)
                current_state = None

        try:
            _LOGGER.info("Loading current forecast for %s", self._post_code)
            current_forecast = await self.hass.async_add_executor_job(self._client.get_forecast, self._post_code)
            _LOGGER.debug("Current forecast: %s", current_forecast)
            if current_state is None:
                current = None
                if current_forecast is not None:
                    current = current_forecast.current
                if current is not None:
                    current_state = CurrentWeather(None, datetime.datetime.now(tz=datetime.UTC), current.currentTemperature, None, None, None, None, None, None, None, None, None, None, None)
        except Exception as e:
            _LOGGER.exception(e)
            raise UpdateFailed(f"Update failed: {e}") from e
        return (current_state, current_forecast)

class SwissPollenDataCoordinator(DataUpdateCoordinator[CurrentPollen | None]):
    """Coordinates loading of pollen data."""

    _client: PollenClient

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self._pollen_station_code = config_entry.data.get(CONF_POLLEN_STATION_CODE)
        self._client = PollenClient()
        update_interval = timedelta(minutes=60)
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval,
            always_update=False)

    async def _async_update_data(self) -> CurrentPollen | None:
        current_state = None
        if self._pollen_station_code is None:
            _LOGGER.warning("Pollen code not set, not loading current state.")
        else:
            _LOGGER.info("Loading current pollen state for %s", self._pollen_station_code)
            try:
                current_state = await self.hass.async_add_executor_job(
                    self._client.get_current_pollen_for_station, self._pollen_station_code)
                _LOGGER.debug("Current pollen: %s", current_state)
            except Exception as e:
                _LOGGER.exception(e)
                raise UpdateFailed(f"Update failed: {e}") from e
        return current_state
