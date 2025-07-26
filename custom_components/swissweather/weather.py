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

from . import SwissWeatherDataCoordinator, get_weather_coordinator_key
from .const import CONF_POST_CODE, CONF_STATION_CODE, DOMAIN
from .meteo import (
    CurrentWeather,
    FloatValue,
    Forecast as MeteoForecast,
    WeatherForecast,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SwissWeatherDataCoordinator = hass.data[DOMAIN][get_weather_coordinator_key(config_entry)]
    async_add_entities(
        [
            SwissWeather(coordinator, config_entry.data[CONF_POST_CODE], config_entry.data.get(CONF_STATION_CODE)),
        ]
    )

class SwissWeather(CoordinatorEntity[SwissWeatherDataCoordinator], WeatherEntity):

    @staticmethod
    def value_or_none(value: FloatValue | None) -> float | None:
        if value is None or len(value) < 2:
            return None
        return value[0]

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
        self._attr_device_info = DeviceInfo(entry_type=DeviceEntryType.SERVICE, name=f"MeteoSwiss at {id_combo}", identifiers={(DOMAIN, f"swissweather-{id_combo}")})
        self._postCode = postCode
        self._attr_attribution = "Source: MeteoSwiss"

    @property
    def _current_state(self) -> CurrentWeather | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data[0]

    @property
    def _current_forecast(self) -> WeatherForecast | None:
        if self.coordinator.data is None or len(self.coordinator.data) < 2:
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
        forecast = self._current_forecast
        if forecast is None or forecast.current is None:
            return None
        return forecast.current.currentCondition

    @property
    def native_temperature(self) -> float | None:
        state = self._current_state
        if state is not None:
            return self.value_or_none(state.airTemperature)
        forecast = self._current_forecast
        if forecast is not None and forecast.current is not None:
            return self.value_or_none(forecast.current.currentTemperature)
        return None

    @property
    def native_temperature_unit(self) -> str | None:
        return UnitOfTemperature.CELSIUS

    @property
    def native_precipitation_unit(self) -> str | None:
        return UnitOfPrecipitationDepth.MILLIMETERS

    @property
    def native_wind_speed(self) -> float | None:
        if self._current_state is not None:
            return self.value_or_none(self._current_state.windSpeed)
        return None

    @property
    def native_wind_speed_unit(self) -> str | None:
        return UnitOfSpeed.KILOMETERS_PER_HOUR

    @property
    def humidity(self) -> float | None:
        if self._current_state is not None:
            return self.value_or_none(self._current_state.relativeHumidity)
        return None

    @property
    def wind_bearing(self) -> float | str | None:
        if self._current_state is not None:
            return self.value_or_none(self._current_state.windDirection)
        return None

    @property
    def native_pressure(self) -> float | None:
        if self._current_state is not None:
            return self.value_or_none(self._current_state.pressureStationLevel)
        return None

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
        if forecast_data is None:
            return None
        return [self.meteo_forecast_to_forecast(entry, False) for entry in forecast_data]

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        _LOGGER.debug("Retrieving hourly forecast.")
        if self._current_forecast is None or self._current_forecast.hourlyForecast is None:
            _LOGGER.info("No hourly forecast available.")
            return None
        now = datetime.datetime.now(tz=datetime.UTC).replace(minute=0, second=0, microsecond=0)
        forecast_data = list(filter(lambda forecast: forecast.timestamp >= now, self._current_forecast.hourlyForecast))
        return [self.meteo_forecast_to_forecast(entry, True) for entry in forecast_data]

    def meteo_forecast_to_forecast(self, meteo_forecast: MeteoForecast, isHourly) -> Forecast:
        if isHourly:
            temperature = self.value_or_none(meteo_forecast.temperatureMean)
            wind_speed = self.value_or_none(meteo_forecast.windSpeed)
            wind_bearing = self.value_or_none(meteo_forecast.windDirection)
            wind_gust_speed = self.value_or_none(meteo_forecast.windGustSpeed)
            sunshine = self.value_or_none(meteo_forecast.sunshine)
        else:
            temperature = meteo_forecast.temperatureMax[0]
            wind_speed = None
            wind_bearing = None
            wind_gust_speed = None
            sunshine = None

        return Forecast(condition=meteo_forecast.condition,
                datetime=meteo_forecast.timestamp.isoformat(),
                precipitation=self.value_or_none(meteo_forecast.precipitation),
                precipitation_probability=self.value_or_none(meteo_forecast.precipitationProbability),
                temperature=temperature,
                templow=self.value_or_none(meteo_forecast.temperatureMin),
                wind_speed=wind_speed,
                wind_gust_speed=wind_gust_speed,
                wind_bearing=wind_bearing,
                sunshine=sunshine)
