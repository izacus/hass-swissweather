"""Constants for the Swiss Weather integration."""

DOMAIN = "swissweather"

CONF_STATION_CODE = "stationCode"
CONF_POLLEN_STATION_CODE = "pollenStationCode"
CONF_POST_CODE = "postCode"
CONF_WEATHER_WARNINGS_NUMBER = "weatherWarningsNumber"

# Optional stations replacing the main station for one group of measurements, keyed like meteo.STATION_GROUP_FIELDS.
CONF_GROUP_STATION_CODES = {
    "temperature": "temperatureStationCode",
    "precipitation": "precipitationStationCode",
    "wind": "windStationCode",
    "pressure": "pressureStationCode",
    "sunshine": "sunshineStationCode",
}
