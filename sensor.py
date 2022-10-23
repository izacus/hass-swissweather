from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

import logging
from decimal import Decimal

from homeassistant.const import (
    DEGREE,
    LENGTH_MILLIMETERS,
    PERCENTAGE,
    PRESSURE_HPA,
    IRRADIATION_WATTS_PER_SQUARE_METER,
    SPEED_KILOMETERS_PER_HOUR,
    TEMP_CELSIUS,
    TIME_MINUTES,
)

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import SwissWeatherDataCoordinator

from .const import CONF_POST_CODE, DOMAIN
from .meteo import CurrentWeather

_LOGGER = logging.getLogger(__name__)

@dataclass
class SwissWeatherSensorEntry:
    key: str
    description: str
    data_function: Callable[[CurrentWeather], StateType | Decimal]
    native_unit: str
    device_class: SensorDeviceClass
    state_class: SensorStateClass

def first_or_none(value):
    if value is None or len(value) < 1:
        return None
    return value[0]

SENSORS: list[SwissWeatherSensorEntry] = [
    SwissWeatherSensorEntry("time", "Time", lambda weather: weather.date, None, SensorDeviceClass.TIMESTAMP, None),
    SwissWeatherSensorEntry("temperature", "Temperature", lambda weather: first_or_none(weather.airTemperature), TEMP_CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("precipitation", "Precipitation", lambda weather: first_or_none(weather.precipitation), LENGTH_MILLIMETERS, None, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("sunshine", "Sunshine", lambda weather: first_or_none(weather.sunshine), TIME_MINUTES, None, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("global_radiation", "Global Radiation", lambda weather: first_or_none(weather.globalRadiation), IRRADIATION_WATTS_PER_SQUARE_METER, None, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("humidity", "Relative Humidity", lambda weather: first_or_none(weather.relativeHumidity), PERCENTAGE, SensorDeviceClass.HUMIDITY, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("dew_point", "Dew Point", lambda weather: first_or_none(weather.dewPoint), TEMP_CELSIUS, None, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("wind_direction", "Wind Direction", lambda weather: first_or_none(weather.windDirection), DEGREE, None, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("wind_speed", "Wind Speed", lambda weather: first_or_none(weather.windSpeed), SPEED_KILOMETERS_PER_HOUR, SensorDeviceClass.SPEED, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("pressure", "Air Pressure", lambda weather: first_or_none(weather.pressureStationLevel), PRESSURE_HPA, SensorDeviceClass.PRESSURE, SensorStateClass.MEASUREMENT),
]

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SwissWeatherDataCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    postCode: str = config_entry.data[CONF_POST_CODE]
    entities: list[SwissWeatherSensor] = [SwissWeatherSensor(postCode, sensorEntry, coordinator) for sensorEntry in SENSORS]
    async_add_entities(entities)

class SwissWeatherSensor(SensorEntity):
    def __init__(self, post_code:str, sensor_entry:SwissWeatherSensorEntry, coordinator:SwissWeatherDataCoordinator) -> None:
        self.entity_description = SensorEntityDescription(key=sensor_entry.key, name=sensor_entry.description, native_unit_of_measurement=sensor_entry.native_unit, device_class=sensor_entry.device_class, state_class=sensor_entry.state_class)
        self._coordinator = coordinator
        self._sensor_entry = sensor_entry        
        self._attr_name = f"{sensor_entry.description} at {post_code}"
        self._attr_unique_id = f"{post_code}.{sensor_entry.key}"
        self._attr_device_info = DeviceInfo(entry_type=DeviceEntryType.SERVICE, identifiers={(DOMAIN, f"swissweather-{post_code}")})

    @property
    def available(self) -> bool:
        return self._coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        """Connect to dispatcher listening for entity data notifications."""
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self) -> None:
        await self._coordinator.async_request_refresh()

    @property
    def native_value(self) -> StateType | Decimal:
        if self._coordinator.data is None:
            return None
        currentState = self._coordinator.data[0]
        return self._sensor_entry.data_function(currentState)