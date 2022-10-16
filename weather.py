from __future__ import annotations

import logging

from types import MappingProxyType
from typing import Any
from config.custom_components.swissweather.meteo import MeteoClient, WeatherForecast, CurrentWeather

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    LENGTH_MILLIMETERS,
    PRESSURE_HPA,
    TEMP_CELSIUS,
    SPEED_KILOMETERS_PER_HOUR
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_POST_CODE, CONF_STATION_CODE

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client = MeteoClient()
    async_add_entities(
        [
            SwissWeather(
                hass,
                client,
                config_entry.data,
                False,
            ),
            SwissWeather(
                hass,
                client,
                config_entry.data,
                True,
            ),
        ]
    )

class SwissWeather(WeatherEntity):

    _current_state : CurrentWeather = None
    _current_forecast : WeatherForecast = None

    def __init__(
        self,
        client: MeteoClient,
        config: MappingProxyType[str, Any],
        hourly: bool,
    ) -> None:
        super().__init__()
        self._client = client
        self._stationCode = config[CONF_STATION_CODE]
        self._postCode = config[CONF_POST_CODE]
        self._hourly = hourly
        self._current_forecast = None

    @property
    def unique_id(self) -> str | None:
        if self._hourly:
            return f"swiss_weather.{self._postCode}.hourly"
        else:
            return f"swiss_weather.{self._postCode}.daily"

    @property
    def name(self):
        if self._hourly:
            return f"Weather at {self._postCode} (Hourly)"
        else:
            return f"Weather at {self._postCode} (Daily)"

    @property
    def condition(self) -> str | None:
        if self._current_forecast is None:
            return None
        return self._current_forecast.current.currentCondition

    @property
    def native_temperature(self) -> float | None:
        if self._current_state is not None and self._current_state.airTemperature is not None:
            return self._current_state.airTemperature[0]
        if self._current_forecast is None:
            return None
        return self._current_forecast.current.currentTemperature[0]

    @property
    def native_temperature_unit(self) -> str | None:
        return TEMP_CELSIUS

    @property
    def native_precipitation_unit(self) -> str | None:
        return LENGTH_MILLIMETERS

    @property
    def native_wind_speed(self) -> float | None:
        if self._current_state is not None:
            return self._current_state.windSpeed[0]
        return None

    @property
    def native_wind_speed_unit(self) -> str | None:
        return SPEED_KILOMETERS_PER_HOUR

    @property
    def humidity(self) -> float | None:
        if self._current_state is None:
            return None
        return self._current_state.relativeHumidity[0]

    @property
    def wind_bearing(self) -> float | str | None:
        if self._current_state is None:
            return None
        return self._current_state.windDirection[0]

    @property
    def native_pressure(self) -> float | None:
        if self._current_state is None:
            return None
        return self._current_state.pressureStationLevel[0]

    @property
    def native_pressure_unit(self) -> str | None:
        return PRESSURE_HPA

    @property
    def forecast(self) -> list[Forecast] | None:
        if self._current_forecast is None:
            return None

        if self._hourly:
            forecast_data = self._current_forecast.hourlyForecast
        else:
            forecast_data = self._current_forecast.dailyForecast
        
        return list(map(lambda entry: self.meteo_forecast_to_forecast(entry), forecast_data))

    def meteo_forecast_to_forecast(self, meteo_forecast) -> Forecast:
        if self._hourly:
            temperature = meteo_forecast.temperatureMean[0]
            wind_speed = meteo_forecast.windSpeed[0]
            wind_bearing = meteo_forecast.windDirection[0]
        else: 
            temperature = meteo_forecast.temperatureMax[0]
            wind_speed = None
            wind_bearing = None

        return Forecast(condition=meteo_forecast.condition, 
                datetime=meteo_forecast.timestamp,
                native_precipitation=meteo_forecast.precipitation[0],
                native_temperature=temperature,
                native_templow=meteo_forecast.temperatureMin[0],
                native_wind_speed=wind_speed,
                wind_bearing=wind_bearing)

    async def async_update(self):
        try:
            if self._stationCode is not None:
                self._current_state = await self.hass.async_add_executor_job(self._client.get_current_weather_for_station, 
                                                                              self._stationCode)
            self._current_forecast = await self.hass.async_add_executor_job(self._client.get_forecast, self._postCode)
        except Exception as e:
            self._current_forecast = None
            _LOGGER.error("Failed to load weather data.")
            _LOGGER.exception(e)