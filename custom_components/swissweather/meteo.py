import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import itertools
import logging
from typing import NewType

import requests

logger = logging.getLogger(__name__)

CURRENT_CONDITION_URL= 'https://data.geo.admin.ch/ch.meteoschweiz.messwerte-aktuell/VQHA80.csv'

FORECAST_URL= "https://app-prod-ws.meteoswiss-app.ch/v1/plzDetail?plz={:<06d}"
FORECAST_USER_AGENT = "android-31 ch.admin.meteoswiss-2160000"

CONDITION_CLASSES = {
    "clear-night": [101],
    "cloudy": [5,35,105,135],
    "fog": [27,28,127,128],
    "hail": [],
    "lightning": [12,112],
    "lightning-rainy": [13,23,24,25,32,113,123,124,125,132],
    "partlycloudy": [2,3,4,102,103,104],
    "pouring": [20,120],
    "rainy": [6,9,14,17,29,33,106,109,114,117,129,133],
    "snowy": [8,11,16,19,22,30,34,108,111,116,119,122,130,134],
    "snowy-rainy": [7,10,15,18,21,31,107,110,115,118,121,131],
    "sunny": [1,26,126],
    "windy": [],
    "windy-variant": [],
    "exceptional": [],
}

ICON_TO_CONDITION_MAP : dict[int, str] =  {i: k for k, v in CONDITION_CLASSES.items() for i in v}

"""
Returns float or None
"""
def to_float(string: str) -> float | None:
    if string is None:
        return None

    try:
        return float(string)
    except ValueError:
        return None

def to_int(string: str) -> int | None:
    if string is None:
        return None

    try:
        return int(string)
    except ValueError:
        return None

FloatValue = NewType('FloatValue', tuple[float | None, str | None])

@dataclass
class StationInfo:
    name: str
    abbreviation: str
    type: str
    altitude: float
    lat: float
    lng: float
    canton: str

    def __str__(self) -> str:
        return f"Station {self.abbreviation} - [Name: {self.name}, Lat: {self.lat}, Lng: {self.lng}, Canton: {self.canton}]"

@dataclass
class CurrentWeather:
    station: StationInfo | None
    date: datetime
    airTemperature: FloatValue | None
    precipitation: FloatValue | None
    sunshine: FloatValue | None
    globalRadiation: FloatValue | None
    relativeHumidity: FloatValue | None
    dewPoint: FloatValue | None
    windDirection: FloatValue | None
    windSpeed: FloatValue | None
    gustPeak1s: FloatValue | None
    pressureStationLevel: FloatValue | None
    pressureSeaLevel: FloatValue | None
    pressureSeaLevelAtStandardAtmosphere: FloatValue | None

@dataclass
class CurrentState:
    currentTemperature: FloatValue
    currentIcon: int
    currentCondition: str | None # None if icon is unrecognized.

@dataclass
class Forecast:
    timestamp: datetime
    icon: int
    condition: str | None # None if icon is unrecognized.
    temperatureMax: FloatValue
    temperatureMin: FloatValue
    precipitation: FloatValue
    precipitationProbability: FloatValue | None
    # Only available for hourly forecast
    temperatureMean: FloatValue | None = None
    windSpeed: FloatValue | None = None
    windDirection: FloatValue | None = None
    windGustSpeed: FloatValue | None = None
    sunshine: FloatValue | None = None

@dataclass
class WeatherForecast(object):
    current: CurrentState | None
    dailyForecast: list[Forecast] | None
    hourlyForecast: list[Forecast] | None
    sunrise: list[datetime] | None
    sunset: list[datetime] | None

class MeteoClient(object):
    language: str = "en"

    """
    Initializes the client.

    Languages available are en, de, fr and it.
    """
    def __init__(self, language="en"):
        self.language = language

    def get_current_weather_for_all_stations(self) -> list[CurrentWeather] | None:
        logger.debug("Retrieving current weather for all stations ...")
        data = self._get_csv_dictionary_for_url(CURRENT_CONDITION_URL)
        weather = []
        for row in data:
            weather.append(self._get_current_data_for_row(row))
        return weather

    def get_current_weather_for_station(self, station: str) -> CurrentWeather | None:
        logger.debug("Retrieving current weather...")
        data = self._get_current_weather_line_for_station(station)
        if data is None:
            logger.warning("Couldn't find data for station %s", station)
            return None

        return self._get_current_data_for_row(data)

    def _get_current_data_for_row(self, csv_row) -> CurrentWeather:
        timestamp = None
        timestamp_raw = csv_row.get('Date', None)
        if timestamp_raw is not None:
            timestamp = datetime.strptime(timestamp_raw, '%Y%m%d%H%M').replace(tzinfo=UTC)

        return CurrentWeather(
            csv_row.get('Station/Location'),
            timestamp,
            (to_float(csv_row.get('tre200s0', None)), "°C") ,
            (to_float(csv_row.get('rre150z0', None)), "mm"),
            (to_float(csv_row.get('sre000z0', None)), "min"),
            (to_float(csv_row.get('gre000z0', None)), "W/m²"),
            (to_float(csv_row.get('ure200s0', None)), '%'),
            (to_float(csv_row.get('tde200s0', None)), '°C'),
            (to_float(csv_row.get('dkl010z0', None)), '°'),
            (to_float(csv_row.get('fu3010z0', None)), 'km/h'),
            (to_float(csv_row.get('fu3010z1', None)), 'km/h'),
            (to_float(csv_row.get('prestas0', None)), 'hPa'),
            (to_float(csv_row.get('prestas0', None)), 'hPa'),
            (to_float(csv_row.get('pp0qnhs0', None)), 'hPa'),
        )


    ## Forecast
    def get_forecast(self, postCode) -> WeatherForecast | None:
        forecastJson = self._get_forecast_json(postCode, self.language)
        logger.debug("Forecast JSON: %s", forecastJson)
        if forecastJson is None:
            return None

        currentState = self._get_current_state(forecastJson)
        dailyForecast = self._get_daily_forecast(forecastJson)
        hourlyForecast = self._get_hourly_forecast(forecastJson)

        sunrises = None
        sunriseJson = forecastJson.get("graph", {}).get("sunrise", None)
        if sunriseJson is not None:
            sunrises = [datetime.fromtimestamp(epoch / 1000, UTC) for epoch in sunriseJson]

        sunsets = None
        sunsetJson = forecastJson.get("graph", {}).get("sunset", None)
        if sunsetJson is not None:
            sunsets = [datetime.fromtimestamp(epoch / 1000, UTC) for epoch in sunsetJson]

        return WeatherForecast(currentState, dailyForecast, hourlyForecast, sunrises, sunsets)

    def _get_current_state(self, forecastJson) -> CurrentState | None:
        if "currentWeather" not in forecastJson:
            return None

        currentIcon = to_int(forecastJson.get('currentWeather', {}).get('icon', None))
        currentCondition = None
        if currentIcon is not None:
            currentCondition = ICON_TO_CONDITION_MAP.get(currentIcon)
        return CurrentState(
            (to_float(forecastJson.get('currentWeather', {}).get('temperature')), "°C"),
            currentIcon, currentCondition)

    def _get_daily_forecast(self, forecastJson) -> list[Forecast] | None:
        forecast: list[Forecast] = []
        if "forecast" not in forecastJson:
            return forecast

        for dailyJson in forecastJson["forecast"]:
            timestamp = None
            if "dayDate" in dailyJson:
                timestamp = datetime.strptime(dailyJson["dayDate"], '%Y-%m-%d')
            icon = to_int(dailyJson.get('iconDay', None))
            condition = ICON_TO_CONDITION_MAP.get(icon)
            temperatureMax = (to_float(dailyJson.get('temperatureMax', None)), "°C")
            temperatureMin = (to_float(dailyJson.get('temperatureMin', None)), "°C")
            precipitation = (to_float(dailyJson.get('precipitation', None)), "mm")
            forecast.append(Forecast(timestamp, icon, condition, temperatureMax, temperatureMin, precipitation, None))
        return forecast

    def _get_hourly_forecast(self, forecastJson) -> list[Forecast] | None:
        graphJson = forecastJson.get("graph", None)
        if graphJson is None:
            return None

        startTimestampEpoch = to_int(graphJson.get('start', None))
        if startTimestampEpoch is None:
            return None
        startTimestamp = datetime.fromtimestamp(startTimestampEpoch / 1000, UTC)


        forecast = []
        temperatureMaxList = [ (value, "°C") for value in graphJson.get("temperatureMax1h", [])]
        temperatureMeanList = [ (value, "°C") for value in graphJson.get("temperatureMean1h", [])]
        temperatureMinList = [ (value, "°C") for value in graphJson.get("temperatureMin1h", [])]
        precipitationList = [ (value, "mm") for value in graphJson.get("precipitation1h", [])]
        windGustSpeedList = [ (value, "km/h") for value in graphJson.get("gustSpeed1h", [])]
        windSpeedList = [ (value, "km/h") for value in graphJson.get("windSpeed1h", [])]
        sunshineList = [ (value, "min/h") for value in graphJson.get("sunshine1h", [])]

        # We get icons only once every 3 hours so we need to expand each elemen 3-times to match
        iconList = list(itertools.chain.from_iterable(itertools.repeat(x, 3) for x in graphJson.get("weatherIcon3h", [])))
        windDirectionlist = list(itertools.chain.from_iterable(itertools.repeat((x, "°"), 3) for x in graphJson.get("windDirection3h", [])))
        precipitationProbabilityList = list(itertools.chain.from_iterable(itertools.repeat((x, "%"), 3) for x in graphJson.get("precipitationProbability3h", [])))

        # This is the minimum amount of data we have
        minForecastHours = min(len(temperatureMaxList), len(temperatureMeanList), len(temperatureMinList), len(precipitationList), len(iconList))
        timestampList = [ startTimestamp + timedelta(hours=value) for value in range(0, minForecastHours) ]

        for ts, icon, tMax, tMean, tMin, precipitation, precipitationProbability, windDirection, windSpeed, windGustSpeed, sunshine in zip(timestampList, iconList, temperatureMaxList,
                                                        temperatureMeanList, temperatureMinList, precipitationList, precipitationProbabilityList, windDirectionlist, windSpeedList, windGustSpeedList, sunshineList, strict=False):
            forecast.append(Forecast(ts, icon, ICON_TO_CONDITION_MAP.get(icon), tMax, tMin, precipitation, precipitationProbability=precipitationProbability, 
                                     windSpeed=windSpeed, windDirection=windDirection, windGustSpeed=windGustSpeed, temperatureMean=tMean, sunshine=sunshine))
        return forecast

    def _get_current_weather_line_for_station(self, station):
        if station is None:
            return None
        return next((row for row in self._get_csv_dictionary_for_url(CURRENT_CONDITION_URL)
            if row['Station/Location'].casefold() == station.casefold()), None)

    def _get_csv_dictionary_for_url(self, url, encoding='utf-8'):
        try:
            logger.debug("Requesting station data...")
            with requests.get(url, stream = True) as r:
                lines = (line.decode(encoding) for line in r.iter_lines())
                yield from csv.DictReader(lines, delimiter=';')
        except requests.exceptions.RequestException as e:
            logger.error("Connection failure.", exc_info=1)
            return None

    def _get_forecast_json(self, postCode, language):
        try:
            url = FORECAST_URL.format(int(postCode))
            logger.debug("Requesting forecast data from %s...", url)
            return requests.get(url, headers =
                { "User-Agent": FORECAST_USER_AGENT,
                    "Accept-Language": language,
                    "Accept": "application/json" }).json()
        except requests.exceptions.RequestException as e:
            logger.error("Connection failure.", exc_info=1)
            return None
