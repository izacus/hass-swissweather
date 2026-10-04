"""Tests for MeteoClient and related helpers in meteo.py."""
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import aiohttp

from custom_components.swissweather.meteo import (
    MISSING_VALUE_SENTINEL,
    MeteoClient,
    WarningLevel,
    WarningType,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def make_mock_aiohttp_response(text: str = "", json_data: dict | None = None, status: int = 200):
    """Create a mock context manager for aiohttp response."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.text = AsyncMock(return_value=text)
    mock_resp.json = AsyncMock(return_value=json_data)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    return mock_ctx


class TestMeteoClient(unittest.IsolatedAsyncioTestCase):
    """Test MeteoClient methods with real live station fixtures (including SMA)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vqha80_content = (FIXTURES_DIR / "vqha80_sample.csv").read_text(encoding="utf-8")
        with open(FIXTURES_DIR / "forecast_800100.json", encoding="utf-8") as f:
            cls.forecast_json = json.load(f)

    async def asyncSetUp(self):
        self.mock_session = MagicMock(spec=aiohttp.ClientSession)
        self.client = MeteoClient(session=self.mock_session, language="en")

    async def test_get_current_weather_for_station_sma(self):
        """Test parsing live SMA station data from VQHA80 CSV."""
        self.mock_session.get.return_value = make_mock_aiohttp_response(text=self.vqha80_content)

        weather = await self.client.async_get_current_weather_for_station("SMA")
        self.assertIsNotNone(weather)
        self.assertEqual(weather.station, "SMA")
        self.assertEqual(weather.date, datetime(2026, 10, 4, 8, 20, tzinfo=UTC))
        self.assertEqual(weather.airTemperature, (16.0, "°C"))
        self.assertEqual(weather.precipitation, (0.0, "mm"))
        self.assertEqual(weather.sunshine, (10.0, "min"))
        self.assertEqual(weather.globalRadiation, (399.0, "W/m²"))
        self.assertEqual(weather.relativeHumidity, (77.4, "%"))
        self.assertEqual(weather.dewPoint, (12.1, "°C"))
        self.assertEqual(weather.windDirection, (255.0, "°"))
        self.assertEqual(weather.windSpeed, (4.0, "km/h"))
        self.assertEqual(weather.gustPeak1s, (7.6, "km/h"))
        self.assertEqual(weather.pressureStationLevel, (957.7, "hPa"))
        self.assertEqual(weather.pressureSeaLevel, (1027.8, "hPa"))
        self.assertEqual(weather.pressureSeaLevelAtStandardAtmosphere, (1029.1, "hPa"))

    async def test_get_current_weather_case_insensitivity(self):
        """Test station matching is case-insensitive."""
        self.mock_session.get.return_value = make_mock_aiohttp_response(text=self.vqha80_content)

        weather = await self.client.async_get_current_weather_for_station("sma")
        self.assertIsNotNone(weather)
        self.assertEqual(weather.station, "SMA")
        self.assertEqual(weather.airTemperature, (16.0, "°C"))

    async def test_get_current_weather_negative_and_missing_values(self):
        """Test station with sub-zero temperatures and missing dash values (JUN)."""
        self.mock_session.get.return_value = make_mock_aiohttp_response(text=self.vqha80_content)

        weather = await self.client.async_get_current_weather_for_station("JUN")
        self.assertIsNotNone(weather)
        self.assertEqual(weather.station, "JUN")
        self.assertEqual(weather.airTemperature, (-1.1, "°C"))
        self.assertEqual(weather.precipitation, (None, "mm"))
        self.assertEqual(weather.dewPoint, (-3.0, "°C"))
        self.assertEqual(weather.pressureSeaLevel, (None, "hPa"))

    async def test_get_current_weather_unknown_or_none_station(self):
        """Test requesting a station not present or None."""
        self.mock_session.get.return_value = make_mock_aiohttp_response(text=self.vqha80_content)

        self.assertIsNone(await self.client.async_get_current_weather_for_station("NONEXISTENT"))
        self.assertIsNone(await self.client.async_get_current_weather_for_station(None))

    async def test_get_current_weather_for_all_stations(self):
        """Test retrieving all stations from the CSV."""
        self.mock_session.get.return_value = make_mock_aiohttp_response(text=self.vqha80_content)

        stations = await self.client.async_get_current_weather_for_all_stations()
        self.assertIsNotNone(stations)
        self.assertEqual(len(stations), 3)
        station_codes = [s.station for s in stations]
        self.assertIn("TAE", station_codes)
        self.assertIn("JUN", station_codes)
        self.assertIn("SMA", station_codes)

    async def test_get_forecast_full(self):
        """Test parsing complete forecast data for postal code 8001 (Zurich)."""
        self.mock_session.get.return_value = make_mock_aiohttp_response(json_data=self.forecast_json)

        forecast = await self.client.async_get_forecast("8001")
        self.assertIsNotNone(forecast)

        # Current state
        current = forecast.current
        self.assertIsNotNone(current)
        self.assertEqual(current.currentTemperature, (15.7, "°C"))
        self.assertEqual(current.currentIcon, 1)
        self.assertEqual(current.currentCondition, "sunny")

        # Daily forecast
        daily = forecast.dailyForecast
        self.assertIsNotNone(daily)
        self.assertEqual(len(daily), 8)
        first_day = daily[0]
        self.assertEqual(first_day.timestamp, datetime(2026, 10, 4, tzinfo=UTC))
        self.assertEqual(first_day.icon, 2)
        self.assertEqual(first_day.condition, "partlycloudy")
        self.assertEqual(first_day.temperatureMax, (22.0, "°C"))
        self.assertEqual(first_day.temperatureMin, (13.0, "°C"))
        self.assertEqual(first_day.precipitation, (0.0, "mm/h"))

        # Hourly forecast
        hourly = forecast.hourlyForecast
        self.assertIsNotNone(hourly)
        self.assertGreater(len(hourly), 0)
        first_hour = hourly[0]
        self.assertEqual(first_hour.temperatureMax, (17.0, "°C"))
        self.assertEqual(first_hour.temperatureMin, (17.0, "°C"))
        self.assertEqual(first_hour.temperatureMean, (17.0, "°C"))
        self.assertEqual(first_hour.windSpeed, (4.2, "km/h"))
        self.assertEqual(first_hour.windGustSpeed, (10.4, "km/h"))
        self.assertEqual(first_hour.windDirection, (155, "°"))
        self.assertEqual(first_hour.precipitationProbability, (0.0, "%"))

        # Sunrises and sunsets
        self.assertIsNotNone(forecast.sunrise)
        self.assertIsNotNone(forecast.sunset)
        self.assertEqual(len(forecast.sunrise), 2)
        self.assertEqual(len(forecast.sunset), 2)
        self.assertEqual(forecast.sunrise[0].tzinfo, UTC)

        # Warnings
        warnings = forecast.warnings
        self.assertIsNotNone(warnings)
        self.assertEqual(len(warnings), 1)
        warning = warnings[0]
        self.assertEqual(warning.warningType, WarningType.FOREST_FIRES)
        self.assertEqual(warning.warningLevel, WarningLevel.SIGNIFICANT_HAZARD)
        self.assertIn("FOEN", warning.text)
        self.assertFalse(warning.outlook)
        self.assertEqual(len(warning.links), 2)
        self.assertEqual(warning.links[0][0], "General recommendations")

    async def test_get_forecast_none_response(self):
        """Test get_forecast when API returns None."""
        self.client._async_get_forecast_json = AsyncMock(return_value=None)
        self.assertIsNone(await self.client.async_get_forecast("8001"))

    def test_current_state_missing_value_sentinel(self):
        """Test that 32767 sentinel value is converted to None."""
        data = {
            "currentWeather": {
                "temperature": MISSING_VALUE_SENTINEL,
                "iconV2": MISSING_VALUE_SENTINEL,
                "icon": MISSING_VALUE_SENTINEL,
            }
        }
        current_state = self.client._get_current_state(data)
        self.assertIsNotNone(current_state)
        self.assertIsNone(current_state.currentTemperature[0])
        self.assertIsNone(current_state.currentIcon)
        self.assertIsNone(current_state.currentCondition)

    def test_current_state_legacy_icon_fallback(self):
        """Test fallback to legacy icon when iconV2 is absent or unrecognized."""
        data = {
            "currentWeather": {
                "temperature": 20.5,
                "iconV2": 9999,
                "icon": 1,
            }
        }
        current_state = self.client._get_current_state(data)
        self.assertIsNotNone(current_state)
        self.assertEqual(current_state.currentIcon, 1)
        self.assertEqual(current_state.currentCondition, "sunny")

    def test_weather_warnings_unknown_type(self):
        """Test that unknown warning types default to UNKNOWN without crashing."""
        data = {
            "warnings": [
                {
                    "warnType": 9999,
                    "warnLevel": 2,
                    "text": "Strange warning",
                    "htmlText": "Strange warning",
                    "outlook": False,
                    "links": [],
                }
            ]
        }
        warnings = self.client._get_weather_warnings(data)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].warningType, WarningType.UNKNOWN)
        self.assertEqual(warnings[0].warningLevel, WarningLevel.MODERATE_HAZARD)

    async def test_csv_connection_failure(self):
        """Test graceful error handling when CSV fetch raises aiohttp.ClientError."""
        self.mock_session.get.side_effect = aiohttp.ClientError("Network down")
        res = await self.client._async_get_csv_rows_for_url("http://fake.url")
        self.assertIsNone(res)

    async def test_csv_timeout_failure(self):
        """Test graceful error handling when CSV fetch raises TimeoutError."""
        self.mock_session.get.side_effect = TimeoutError("Timed out")
        res = await self.client._async_get_csv_rows_for_url("http://fake.url")
        self.assertIsNone(res)

    async def test_csv_http_error(self):
        """Test graceful error handling when CSV fetch returns non-200 HTTP status."""
        self.mock_session.get.return_value = make_mock_aiohttp_response(status=500, text="Internal Server Error")
        res = await self.client._async_get_csv_rows_for_url("http://fake.url")
        self.assertIsNone(res)

    async def test_forecast_json_connection_failure(self):
        """Test graceful error handling when forecast fetch raises TimeoutError."""
        self.mock_session.get.side_effect = TimeoutError("Timed out")
        res = await self.client._async_get_forecast_json("8001", "en")
        self.assertIsNone(res)

    async def test_forecast_json_http_error(self):
        """Test graceful error handling when forecast fetch returns HTTP 404 or 500."""
        self.mock_session.get.return_value = make_mock_aiohttp_response(status=404)
        res = await self.client._async_get_forecast_json("8001", "en")
        self.assertIsNone(res)

    async def test_forecast_json_broken_syntax(self):
        """Test graceful error handling when forecast endpoint returns malformed/broken JSON."""
        mock_ctx = make_mock_aiohttp_response(status=200)
        # Mock r.json to raise json.JSONDecodeError
        mock_resp = await mock_ctx.__aenter__()
        mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)
        self.mock_session.get.return_value = mock_ctx

        res = await self.client._async_get_forecast_json("8001", "en")
        self.assertIsNone(res)

    async def test_csv_broken_headers_returns_none_for_station(self):
        """Test CSV with corrupted or HTML error response headers does not crash."""
        html_payload = "<html><body>502 Bad Gateway</body></html>"
        self.mock_session.get.return_value = make_mock_aiohttp_response(text=html_payload)

        res = await self.client.async_get_current_weather_for_station("SMA")
        self.assertIsNone(res)

    async def test_csv_row_corrupted_timestamp_skipped(self):
        """Test that rows with corrupted/invalid timestamps are skipped as datapoints."""
        # CSV with two stations: one with valid timestamp, one with corrupted date format
        csv_data = (
            "Station/Location;Date;tre200s0;rre150z0;sre000z0;gre000z0;ure200s0;tde200s0;dkl010z0;fu3010z0;fu3010z1;prestas0;pp0qffs0;pp0qnhs0\n"
            "SMA;202610040820;16.0;0.0;10;399;77.4;12.1;255;4.0;7.6;957.7;1027.8;1029.1\n"
            "BAD;2026-INVALID-DATE;10.0;0.0;0;100;80.0;8.0;180;5.0;8.0;960.0;1020.0;1022.0\n"
        )
        self.mock_session.get.return_value = make_mock_aiohttp_response(text=csv_data)

        # In all stations, BAD station must be skipped
        stations = await self.client.async_get_current_weather_for_all_stations()
        self.assertIsNotNone(stations)
        self.assertEqual(len(stations), 1)
        self.assertEqual(stations[0].station, "SMA")

        # Querying the station with corrupted timestamp directly returns None
        self.assertIsNone(await self.client.async_get_current_weather_for_station("BAD"))

    async def test_csv_row_missing_timestamp_skipped(self):
        """Test that rows with empty or missing Date column are skipped."""
        csv_data = (
            "Station/Location;Date;tre200s0\n"
            "SMA;;16.0\n"
        )
        self.mock_session.get.return_value = make_mock_aiohttp_response(text=csv_data)

        stations = await self.client.async_get_current_weather_for_all_stations()
        self.assertEqual(len(stations), 0)
        self.assertIsNone(await self.client.async_get_current_weather_for_station("SMA"))

    def test_daily_forecast_corrupted_timestamp_skipped(self):
        """Test that daily forecast items with corrupted dayDate are skipped as datapoints."""
        data = {
            "forecast": [
                {
                    "dayDate": "2026-10-04",
                    "iconDay": 1,
                    "temperatureMax": 20.0,
                    "temperatureMin": 10.0,
                },
                {
                    "dayDate": "not-a-valid-date",
                    "iconDay": 2,
                    "temperatureMax": 18.0,
                    "temperatureMin": 8.0,
                },
                {
                    # Missing dayDate entirely
                    "iconDay": 3,
                    "temperatureMax": 15.0,
                    "temperatureMin": 5.0,
                },
            ]
        }
        daily = self.client._get_daily_forecast(data)
        self.assertIsNotNone(daily)
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily[0].timestamp, datetime(2026, 10, 4, tzinfo=UTC))
        self.assertEqual(daily[0].icon, 1)

    def test_hourly_forecast_corrupted_start_timestamp(self):
        """Test that hourly forecast returns None if start timestamp is missing or corrupted."""
        data_missing_start = {"graph": {"start": None}}
        self.assertIsNone(self.client._get_hourly_forecast(data_missing_start))

        data_corrupted_start = {"graph": {"start": "not_an_epoch"}}
        self.assertIsNone(self.client._get_hourly_forecast(data_corrupted_start))

    def test_hourly_forecast_null_and_empty_lists(self):
        """Test hourly forecast handles null / empty graph lists without crashing."""
        data = {
            "graph": {
                "start": 1700000000000,
                "temperatureMax1h": [15.0],
                "temperatureMean1h": [14.0],
                "temperatureMin1h": [13.0],
                "precipitation1h": [],
                "precipitation10m": None,
                "weatherIcon3h": None,
                "windDirection3h": None,
                "precipitationProbability3h": None,
            }
        }
        hourly = self.client._get_hourly_forecast(data)
        self.assertEqual(hourly, [])

    async def test_sunrise_sunset_corrupted_epoch(self):
        """Test sunrise and sunset epoch parsing skips corrupted entries without crashing."""
        data = {
            "graph": {
                "sunrise": ["corrupted", 1759556820000],
                "sunset": [None, 1759600020000],
            }
        }
        self.client._async_get_forecast_json = AsyncMock(return_value=data)
        forecast = await self.client.async_get_forecast("8001")
        self.assertIsNotNone(forecast)
        self.assertIsNotNone(forecast.sunrise)
        self.assertEqual(len(forecast.sunrise), 1)
        self.assertIsNotNone(forecast.sunset)
        self.assertEqual(len(forecast.sunset), 1)

    def test_weather_warnings_corrupted_entries(self):
        """Test warning list with non-dict items, corrupted dates, and malformed links."""
        data = {
            "warnings": [
                "not_a_dict_warning",
                {
                    "warnType": 1,
                    "warnLevel": 2,
                    "validFrom": "invalid_epoch",
                    "validTo": None,
                    "links": None,
                },
                {
                    "warnType": 2,
                    "warnLevel": 3,
                    "links": ["not_a_dict_link", {"text": "Valid Link", "url": "https://example.com"}],
                }
            ]
        }
        warnings = self.client._get_weather_warnings(data)
        self.assertEqual(len(warnings), 2)
        self.assertEqual(warnings[0].validFrom, None)
        self.assertEqual(warnings[0].links, [])
        self.assertEqual(warnings[1].links, [("Valid Link", "https://example.com")])


if __name__ == "__main__":
    unittest.main()

