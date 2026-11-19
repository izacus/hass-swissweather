"""Tests for the SwissWeather weather entity."""
import datetime
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from custom_components.swissweather.weather import SwissWeather


class TestSwissWeatherEntity(unittest.TestCase):
    """Test current values exposed by the weather entity."""

    def test_current_gust_and_dew_point(self):
        """Test that gust speed and dew point come from the current station data."""
        current = MagicMock(gustPeak1s=(7.6, "km/h"), dewPoint=(12.1, "°C"))
        coordinator = MagicMock(data=(current, None))
        entity = SwissWeather(coordinator, "8001", "SMA")
        self.assertEqual(entity.native_wind_gust_speed, 7.6)
        self.assertEqual(entity.native_dew_point, 12.1)

    def test_no_data(self):
        """Test that gust speed and dew point are None without data."""
        coordinator = MagicMock(data=None)
        entity = SwissWeather(coordinator, "8001", "SMA")
        self.assertIsNone(entity.native_wind_gust_speed)
        self.assertIsNone(entity.native_dew_point)


class TestSwissWeatherForecast(unittest.IsolatedAsyncioTestCase):
    """Test the forecasts exposed by the weather entity."""

    def setUp(self):
        self.timestamp = datetime.datetime.now(tz=datetime.UTC).replace(
            minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
        hourly = MagicMock(timestamp=self.timestamp, condition="sunny",
                           temperatureMean=(17.0, "°C"))
        daily = MagicMock(timestamp=self.timestamp, condition="rainy",
                          temperatureMax=(20.0, "°C"), temperatureMin=(9.0, "°C"))
        forecast = MagicMock(hourlyForecast=[hourly], dailyForecast=[daily])
        self.entity = SwissWeather(MagicMock(data=(None, forecast)), "8001", "SMA")

    async def test_hourly_forecast(self):
        """Test the hourly forecast."""
        forecast = await self.entity.async_forecast_hourly()
        self.assertEqual(len(forecast), 1)
        self.assertEqual(forecast[0]["datetime"], self.timestamp.isoformat())
        self.assertEqual(forecast[0]["condition"], "sunny")
        self.assertEqual(forecast[0]["temperature"], 17.0)

    async def test_daily_forecast(self):
        """Test the daily forecast."""
        forecast = await self.entity.async_forecast_daily()
        self.assertEqual(len(forecast), 1)
        self.assertEqual(forecast[0]["condition"], "rainy")
        self.assertEqual(forecast[0]["temperature"], 20.0)
        self.assertEqual(forecast[0]["templow"], 9.0)

    async def test_no_forecast(self):
        """Test that forecasts are None without data."""
        entity = SwissWeather(MagicMock(data=None), "8001", "SMA")
        self.assertIsNone(await entity.async_forecast_hourly())
        self.assertIsNone(await entity.async_forecast_daily())
