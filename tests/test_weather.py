"""Tests for the SwissWeather weather entity."""
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
