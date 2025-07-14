from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import logging
from typing import Callable

from propcache.api import cached_property

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_CUBIC_METER,
    DEGREE,
    PERCENTAGE,
    UnitOfIrradiance,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import (
    SwissPollenDataCoordinator,
    SwissWeatherDataCoordinator,
    get_pollen_coordinator_key,
    get_weather_coordinator_key,
)
from .const import CONF_POLLEN_STATION_CODE, CONF_POST_CODE, CONF_STATION_CODE, DOMAIN
from .meteo import CurrentWeather
from .pollen import CurrentPollen, PollenLevel

_LOGGER = logging.getLogger(__name__)

@dataclass
class SwissWeatherSensorEntry:
    key: str
    description: str
    data_function: Callable[[CurrentWeather], StateType | Decimal]
    native_unit: str
    device_class: SensorDeviceClass
    state_class: SensorStateClass

@dataclass
class SwissPollenSensorEntry:
    key: str
    description: str
    data_function: Callable[[CurrentPollen], StateType | Decimal]
    device_class: SensorDeviceClass | None

def first_or_none(value):
    if value is None or len(value) < 1:
        return None
    return value[0]

SENSORS: list[SwissWeatherSensorEntry] = [
    SwissWeatherSensorEntry("time", "Time", lambda weather: weather.date, None, SensorDeviceClass.TIMESTAMP, None),
    SwissWeatherSensorEntry("temperature", "Temperature", lambda weather: first_or_none(weather.airTemperature), UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("precipitation", "Precipitation", lambda weather: first_or_none(weather.precipitation), UnitOfPrecipitationDepth.MILLIMETERS, None, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("sunshine", "Sunshine", lambda weather: first_or_none(weather.sunshine), UnitOfTime.MINUTES, None, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("global_radiation", "Global Radiation", lambda weather: first_or_none(weather.globalRadiation), UnitOfIrradiance.WATTS_PER_SQUARE_METER, None, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("humidity", "Relative Humidity", lambda weather: first_or_none(weather.relativeHumidity), PERCENTAGE, SensorDeviceClass.HUMIDITY, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("dew_point", "Dew Point", lambda weather: first_or_none(weather.dewPoint), UnitOfTemperature.CELSIUS, None, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("wind_direction", "Wind Direction", lambda weather: first_or_none(weather.windDirection), DEGREE, None, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("wind_speed", "Wind Speed", lambda weather: first_or_none(weather.windSpeed), UnitOfSpeed.KILOMETERS_PER_HOUR, SensorDeviceClass.SPEED, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("gust_peak1s", "Wind Gusts - Peak 1s", lambda weather: first_or_none(weather.gustPeak1s), UnitOfSpeed.KILOMETERS_PER_HOUR, SensorDeviceClass.SPEED, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("pressure", "Air Pressure", lambda weather: first_or_none(weather.pressureStationLevel), UnitOfPressure.HPA, SensorDeviceClass.PRESSURE, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("pressure_qff", "Air Pressure - Sea Level (QFF)", lambda weather: first_or_none(weather.pressureSeaLevel), UnitOfPressure.HPA, SensorDeviceClass.PRESSURE, SensorStateClass.MEASUREMENT),
    SwissWeatherSensorEntry("pressure_qnh", "Air Pressure - Sea Level (QNH)", lambda weather: first_or_none(weather.pressureSeaLevelAtStandardAtmosphere), UnitOfPressure.HPA, SensorDeviceClass.PRESSURE, SensorStateClass.MEASUREMENT)
]

POLLEN_SENSORS: list[SwissPollenSensorEntry] = [
    SwissPollenSensorEntry("pollen-time", "Pollen Time", lambda pollen: pollen.timestamp, SensorDeviceClass.TIMESTAMP),
    SwissPollenSensorEntry("birch", "Pollen - Birch", lambda pollen: first_or_none(pollen.birch), None),
    SwissPollenSensorEntry("grasses", "Pollen - Grasses", lambda pollen: first_or_none(pollen.grasses), None),
    SwissPollenSensorEntry("alder", "Pollen - Alder", lambda pollen: first_or_none(pollen.alder), None),
    SwissPollenSensorEntry("hazel", "Pollen - Hazel", lambda pollen: first_or_none(pollen.hazel), None),
    SwissPollenSensorEntry("beech", "Pollen - Beech", lambda pollen: first_or_none(pollen.beech), None),
    SwissPollenSensorEntry("ash", "Pollen - Ash", lambda pollen: first_or_none(pollen.ash), None),
    SwissPollenSensorEntry("oak", "Pollen - Oak", lambda pollen: first_or_none(pollen.oak), None),
]

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SwissWeatherDataCoordinator = hass.data[DOMAIN][get_weather_coordinator_key(config_entry)]
    postCode: str = config_entry.data[CONF_POST_CODE]
    stationCode: str = config_entry.data.get(CONF_STATION_CODE)
    pollenStationCode: str = config_entry.data.get(CONF_POLLEN_STATION_CODE)
    if stationCode is None:
            id_combo = f"{postCode}"
    else:
        id_combo = f"{postCode}-{stationCode}"
    deviceInfo = DeviceInfo(entry_type=DeviceEntryType.SERVICE, name=f"MeteoSwiss at {id_combo}", identifiers={(DOMAIN, f"swissweather-{id_combo}")})
    entities: list[SwissWeatherSensor|SwissPollenSensor] = [SwissWeatherSensor(postCode, deviceInfo, sensorEntry, coordinator) for sensorEntry in SENSORS]

    if pollenStationCode is not None:
        pollenCoordinator = hass.data[DOMAIN][get_pollen_coordinator_key(config_entry)]
        entities += [SwissPollenSensor(postCode, pollenStationCode, deviceInfo, sensorEntry, pollenCoordinator) for sensorEntry in POLLEN_SENSORS]
        entities += [SwissPollenLevelSensor(postCode, pollenStationCode, deviceInfo, sensorEntry, pollenCoordinator) for sensorEntry in POLLEN_SENSORS if sensorEntry.device_class is None]

    async_add_entities(entities)


class SwissWeatherSensor(CoordinatorEntity[SwissWeatherDataCoordinator], SensorEntity):
    def __init__(self, post_code:str, device_info: DeviceInfo, sensor_entry:SwissWeatherSensorEntry, coordinator:SwissWeatherDataCoordinator) -> None:
        super().__init__(coordinator)
        self.entity_description = SensorEntityDescription(key=sensor_entry.key,
                                                          name=sensor_entry.description,
                                                          native_unit_of_measurement=sensor_entry.native_unit,
                                                          device_class=sensor_entry.device_class,
                                                          state_class=sensor_entry.state_class)
        self._sensor_entry = sensor_entry
        self._attr_name = f"{sensor_entry.description} at {post_code}"
        self._attr_unique_id = f"{post_code}.{sensor_entry.key}"
        self._attr_device_info = device_info
        self._attr_attribution = "Source: MeteoSwiss"

    @property
    def native_value(self) -> StateType | Decimal:
        if self.coordinator.data is None:
            return None
        currentState = self.coordinator.data[0]
        return self._sensor_entry.data_function(currentState)

class SwissPollenSensor(CoordinatorEntity[SwissPollenDataCoordinator], SensorEntity):

    def __init__(self, post_code:str, station_code: str, device_info: DeviceInfo, sensor_entry:SwissPollenSensorEntry, coordinator:SwissPollenDataCoordinator) -> None:
        super().__init__(coordinator)
        state_class = SensorStateClass.MEASUREMENT
        unit = CONCENTRATION_PARTS_PER_CUBIC_METER
        if sensor_entry.device_class is SensorDeviceClass.TIMESTAMP:
            state_class = None
            unit = None
        self.entity_description = SensorEntityDescription(key=sensor_entry.key,
                                                        name=sensor_entry.description,
                                                        native_unit_of_measurement=unit,
                                                        state_class=state_class)
        self._sensor_entry = sensor_entry
        self._attr_name = f"{sensor_entry.description} at {post_code} - {station_code}"
        self._attr_unique_id = f"pollen-{post_code}.{sensor_entry.key}"
        self._attr_device_info = device_info
        self._attr_device_class = sensor_entry.device_class
        self._attr_suggested_display_precision = 0
        self._attr_attribution = "Source: MeteoSwiss"

    @property
    def native_value(self) -> StateType | Decimal:
        if self.coordinator.data is None:
            return None
        currentState = self.coordinator.data
        return self._sensor_entry.data_function(currentState)

    @cached_property
    def icon(self):
        return "mdi:flower-pollen"

class SwissPollenLevelSensor(CoordinatorEntity[SwissPollenDataCoordinator], SensorEntity):

    def __init__(self, post_code:str, station_code: str, device_info: DeviceInfo, sensor_entry:SwissPollenSensorEntry, coordinator:SwissPollenDataCoordinator) -> None:
        super().__init__(coordinator)
        self.entity_description = SensorEntityDescription(key=sensor_entry.key,
                                                        name=sensor_entry.description,
                                                        device_class=SensorDeviceClass.ENUM)
        self._sensor_entry = sensor_entry
        self._attr_name = f"{sensor_entry.description} level at {post_code} - {station_code}"
        self._attr_unique_id = f"pollen-level-{post_code}.{sensor_entry.key}"
        self._attr_device_info = device_info
        self._attr_options = [PollenLevel.NONE, PollenLevel.LOW, PollenLevel.MEDIUM, PollenLevel.STRONG, PollenLevel.VERY_STRONG]
        self._attr_attribution = "Source: MeteoSwiss"

    @property
    def native_value(self) -> StateType | Decimal:
        if self.coordinator.data is None:
            return None
        currentState = self.coordinator.data
        value = self._sensor_entry.data_function(currentState)
        if value is not None:
            if value == 0:
                return PollenLevel.NONE
            elif value <= 10:
                return PollenLevel.LOW
            elif value <= 70:
                return PollenLevel.MEDIUM
            elif value <= 250:
                return PollenLevel.STRONG
            else:
                return PollenLevel.VERY_STRONG
        return None

    @cached_property
    def icon(self):
        return "mdi:flower-pollen-outline"
