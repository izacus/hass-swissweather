from __future__ import annotations

import datetime
import logging

from homeassistant.components.weather import Forecast, WeatherEntity
from homeassistant.components.weather.const import WeatherEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SwissWeatherDataCoordinator
from .const import CONF_POST_CODE, CONF_STATION_CODE, DOMAIN
from .meteo import CurrentWeather, WeatherForecast

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SwissWeatherDataCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [
            SwissWeather(coordinator, config_entry.data[CONF_POST_CODE], config_entry.data.get(CONF_STATION_CODE)),
        ]
    )

class SwissWeather(CoordinatorEntity[SwissWeatherDataCoordinator], WeatherEntity):

    def __init__(
        self,
        coordinator: SwissWeatherDataCoordinator,
        postCode: str,
        stationCode: str,
    ) -> None:
        super().__init__(coordinator)
        if stationCode is None:
            id_combo = f"{postCode}"
        else:
            id_combo = f"{postCode}-{stationCode}"
        self._postCode = postCode
        self._attr_device_info = DeviceInfo(entry_type=DeviceEntryType.SERVICE,
                                            name=f"MeteoSwiss at {id_combo}",
                                            suggested_area=None,
                                            identifiers={(DOMAIN, f"swissweather-{id_combo}")})

    @property
    def _current_state(self) -> CurrentWeather:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data[0]

    @property
    def _current_forecast(self) -> WeatherForecast:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data[1]

    @property
    def unique_id(self) -> str | None:        
        return f"swiss_weather.{self._postCode}"

    @property
    def name(self):        
        return f"Weather at {self._postCode}"

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
        return UnitOfTemperature.CELSIUS

    @property
    def native_precipitation_unit(self) -> str | None:
        return UnitOfPrecipitationDepth.MILLIMETERS

    @property
    def native_wind_speed(self) -> float | None:
        if self._current_state is not None:
            return self._current_state.windSpeed[0]
        return None

    @property
    def native_wind_speed_unit(self) -> str | None:
        return UnitOfSpeed.KILOMETERS_PER_HOUR

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
        return UnitOfPressure.HPA

    @property
    def supported_features(self) -> int | None:
        return WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY

    async def async_forecast_daily(self) -> list[Forecast] | None:
        _LOGGER.debug("Retrieving daily forecast.")
        if self._current_forecast is None:
            _LOGGER.info("No daily forecast available.")
            return None
        forecast_data = self._current_forecast.dailyForecast
        return [self.meteo_forecast_to_forecast(entry, False) for entry in forecast_data]

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        _LOGGER.debug("Retrieving hourly forecast.")
        if self._current_forecast is None:
            _LOGGER.info("No hourly forecast available.")
            return None
        now = datetime.datetime.now(tz=datetime.UTC).replace(minute=0, second=0, microsecond=0)
        forecast_data = list(filter(lambda forecast: forecast.timestamp >= now, self._current_forecast.hourlyForecast))
        return [self.meteo_forecast_to_forecast(entry, True) for entry in forecast_data]

    def meteo_forecast_to_forecast(self, meteo_forecast, isHourly) -> Forecast:
        if isHourly:
            temperature = meteo_forecast.temperatureMean[0]
            wind_speed = meteo_forecast.windSpeed[0]
            wind_bearing = meteo_forecast.windDirection[0]
            wind_gust_speed = meteo_forecast.windGustSpeed[0]
            sunshine = meteo_forecast.sunshine[0]
        else:
            temperature = meteo_forecast.temperatureMax[0]
            wind_speed = None
            wind_bearing = None
            wind_gust_speed = None
            sunshine = None

        return Forecast(condition=meteo_forecast.condition,
                datetime=meteo_forecast.timestamp.isoformat(),
                native_precipitation=meteo_forecast.precipitation[0],
                native_temperature=temperature,
                native_templow=meteo_forecast.temperatureMin[0],
                native_wind_speed=wind_speed,
                native_wind_gust_speed=wind_gust_speed,
                wind_bearing=wind_bearing,
                sunshine=sunshine)
