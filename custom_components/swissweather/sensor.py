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
    MATCH_ALL,
    PERCENTAGE,
    UnitOfIrradiance,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
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
from .const import (
    CONF_POLLEN_STATION_CODE,
    CONF_POST_CODE,
    CONF_STATION_CODE,
    CONF_WEATHER_WARNINGS_NUMBER,
    DOMAIN,
)
from .meteo import CurrentWeather, Warning, WarningLevel, WarningType
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
    numberOfWeatherWarnings: int = config_entry.data.get(CONF_WEATHER_WARNINGS_NUMBER)
    # Backwards compat
    if numberOfWeatherWarnings is None:
        numberOfWeatherWarnings = 1
    else:
        numberOfWeatherWarnings = int(numberOfWeatherWarnings)

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

    entities.append(SwissWeatherWarningsSensor(postCode, deviceInfo, coordinator))
    for i in range(0, numberOfWeatherWarnings):
        entities.append(SwissWeatherSingleWarningSensor(postCode, i, deviceInfo, coordinator))
        entities.append(SwissWeatherSingleWarningLevelSensor(postCode, i, deviceInfo, coordinator))
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

def get_warning_enum_to_name(value):
    if value is None:
        return None
    return value.name.replace('_', ' ').capitalize()

def get_warnings_from_coordinator(coordinator_data) -> list[Warning] | None:
    if coordinator_data is None or len(coordinator_data) < 2:
        return None
    return coordinator_data[1].warnings

def get_color_for_warning_level(level: WarningLevel) -> str:
    """Returns icon color for the corresponding warning level."""
    if level is None:
        return "gray"
    if level in (WarningLevel.NO_OR_MINIMAL_HAZARD, WarningLevel.NO_DANGER):
        return "gray"
    if level == WarningLevel.MODERATE_HAZARD:
        return "amber"
    return "red"

class SwissWeatherWarningsSensor(CoordinatorEntity[SwissWeatherDataCoordinator], SensorEntity):
    """Shows count of current alterts and their content as attributes."""

    def __init__(self, post_code:str, device_info: DeviceInfo, coordinator:SwissWeatherDataCoordinator) -> None:
        super().__init__(coordinator)
        self.entity_description = SensorEntityDescription(key="warnings",
                                                          name="Weather Warnings")
        self._attr_name = f"Weather warnings at {post_code}"
        self._attr_unique_id = f"{post_code}.warnings"
        self._attr_device_info = device_info
        self._attr_attribution = "Source: MeteoSwiss"
        self._attr_suggested_display_precision = 0
        # We don't want recorder to record any attributes because that will explode the database.
        self._entity_component_unrecorded_attributes = MATCH_ALL

    @property
    def native_value(self) -> StateType | Decimal:
        if self.coordinator.data is None or len(self.coordinator.data) < 2:
            return None

        warnings = get_warnings_from_coordinator(self.coordinator.data)
        if warnings is None:
            return 0
        return len(warnings)

    @property
    def extra_state_attributes(self) -> dict[str, any] | None:
        """Return additional state attributes."""
        warnings = get_warnings_from_coordinator(self.coordinator.data)
        if warnings is None:
            return None

        links = []
        for warning in warnings:
            for link in warning.links:
                links.append(link[1])

        return { 'warning_types': [get_warning_enum_to_name(warning.warningType) for warning in warnings],
                 'warning_levels': [get_warning_enum_to_name(warning.warningLevel) for warning in warnings],
                 'warning_levels_numeric': [warning.warningLevel for warning in warnings],
                 'warning_valid_from': [warning.validFrom for warning in warnings],
                 'warning_valid_to': [warning.validTo for warning in warnings],
                 'warning_texts': [warning.text for warning in warnings],
                 'warning_links': links }

    @cached_property
    def icon(self):
        return "mdi:alert"

class SwissWeatherSingleWarningSensor(CoordinatorEntity[SwissWeatherDataCoordinator], SensorEntity):
    """Shows type and detail of a weather warning."""

    index = 0

    def __init__(self, post_code:str, index:int, device_info: DeviceInfo, coordinator:SwissWeatherDataCoordinator) -> None:
        super().__init__(coordinator)
        if index == 0:
            key = "warnings.most_severe"
            name = "Most severe weather warning"
            attr_name = f"Most severe weather warning at {post_code}"
        else:
            key = f"warnings.{index}"
            name = f"Weather warning {index + 1}"
            attr_name  = f"Weather warning {index + 1} at {post_code}"

        self.index = index
        self.entity_description = SensorEntityDescription(key=key,
                                                          name=name,
                                                          device_class=SensorDeviceClass.ENUM)
        self._attr_name = attr_name
        self._attr_unique_id = f"{post_code}.warning.{index}"
        self._attr_device_info = device_info
        self._attr_attribution = "Source: MeteoSwiss"
        self._attr_options = [get_warning_enum_to_name(warningType) for warningType in WarningType]
        self._entity_component_unrecorded_attributes = MATCH_ALL

    def _get_warning(self) -> Warning | None:
        warnings = get_warnings_from_coordinator(self.coordinator.data)
        if warnings is None:
            return None
        if len(warnings) < self.index + 1:
            return None
        return warnings[self.index]

    @property
    def native_value(self) -> StateType | Decimal:
        warning = self._get_warning()
        if warning is None:
            return None
        return get_warning_enum_to_name(warning.warningType)

    @property
    def extra_state_attributes(self) -> dict[str, any] | None:
        """Return additional state attributes."""
        warning = self._get_warning()
        if warning is None:
            return None

        return {
            'level': get_warning_enum_to_name(warning.warningLevel),
            'level_numeric': warning.warningLevel,
            'text': warning.text,
            'html_text': warning.htmlText,
            'valid_from': warning.validFrom,
            'valid_to': warning.validTo,
            'links': warning.links,
            'outlook': warning.outlook,
            'icon_color': get_color_for_warning_level(warning.warningLevel)
        }

    @property
    def available(self) -> bool:
        warning = self._get_warning()
        return warning is not None

    @cached_property
    def icon(self):
        return "mdi:alert"

class SwissWeatherSingleWarningLevelSensor(CoordinatorEntity[SwissWeatherDataCoordinator], SensorEntity):
    """Shows severity of the weather warning."""
    index = 0

    def __init__(self, post_code:str, index:int, device_info: DeviceInfo, coordinator:SwissWeatherDataCoordinator) -> None:
        super().__init__(coordinator)
        if index == 0:
            key = "warnings.most_severe.level"
            name = "Most severe weather warning level"
            attr_name = f"Most severe weather warning level at {post_code}"
        else:
            key = f"warnings.{index}"
            name = f"Weather warning level {index + 1}"
            attr_name  = f"Weather warning {index + 1} level at {post_code}"

        self.index = index
        self.entity_description = SensorEntityDescription(key=key,
                                                          name=name,
                                                          device_class=SensorDeviceClass.ENUM)
        self._attr_name = attr_name
        self._attr_unique_id = f"{post_code}.warning.level.{index}"
        self._attr_device_info = device_info
        self._attr_attribution = "Source: MeteoSwiss"
        self._attr_options = [get_warning_enum_to_name(warningType) for warningType in WarningLevel]

    def _get_warning(self) -> Warning | None:
        warnings = get_warnings_from_coordinator(self.coordinator.data)
        if warnings is None:
            return None
        if len(warnings) < self.index + 1:
            return None
        return warnings[self.index]

    @property
    def native_value(self) -> StateType | Decimal:
        warning = self._get_warning()
        if warning is None:
            return None
        return get_warning_enum_to_name(warning.warningLevel)

    @property
    def available(self) -> bool:
        warning = self._get_warning()
        return warning is not None

    @property
    def extra_state_attributes(self) -> dict[str, any] | None:
        """Return additional state attributes."""
        warning = self._get_warning()
        if warning is None:
            return None
        return {
            'numeric': warning.warningLevel,
            'icon_color': get_color_for_warning_level(warning.warningLevel)
        }

    @cached_property
    def icon(self):
        return "mdi:alert"

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

def get_color_for_pollen_level(level: int) -> str:
    """Returns icon color for the corresponding warning level."""
    if level is not None:
        if level <= 10:
            return "gray"
        elif level <= 70:
            return "amber"
        elif level <= 250:
            return "red"
    return "gray"

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
        self._entity_component_unrecorded_attributes = MATCH_ALL

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

    @property
    def extra_state_attributes(self) -> dict[str, any] | None:
        """Return additional state attributes."""
        if self.coordinator.data is None:
            return None
        currentState = self.coordinator.data
        value = self._sensor_entry.data_function(currentState)
        return {
            'icon_color': get_color_for_pollen_level(value)
        }

    @cached_property
    def icon(self):
        return "mdi:flower-pollen-outline"
