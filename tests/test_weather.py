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

    def test_coordinator_update_pushes_forecast_to_subscribers(self):
        """Test that a coordinator update also pushes the forecast to subscribers."""
        coordinator = MagicMock(data=None)
        entity = SwissWeather(coordinator, "8001", "SMA")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        update_listeners = object()
        entity.async_update_listeners = MagicMock(return_value=update_listeners)

        entity._handle_coordinator_update()

        entity.async_write_ha_state.assert_called_once_with()
        entity.async_update_listeners.assert_called_once_with(None)
        coordinator.config_entry.async_create_task.assert_called_once_with(
            entity.hass, update_listeners
        )

    def test_coordinator_update_without_config_entry_pushes_forecast(self):
        """Test the forecast push falls back to hass when there is no config entry."""
        coordinator = MagicMock(data=None, config_entry=None)
        coordinator.name = "swissweather"
        entity = SwissWeather(coordinator, "8001", "SMA")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        update_listeners = object()
        entity.async_update_listeners = MagicMock(return_value=update_listeners)

        entity._handle_coordinator_update()

        entity.async_update_listeners.assert_called_once_with(None)
        entity.hass.async_create_task.assert_called_once_with(
            update_listeners, "swissweather"
        )
