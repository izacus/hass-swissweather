"""Tests for PollenClient and pollen levels in pollen.py."""
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

from custom_components.swissweather.pollen import (
    PollenClient,
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


class TestPollenClient(unittest.IsolatedAsyncioTestCase):
    """Test PollenClient methods with real station fixtures (including PZH)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stations_csv = (FIXTURES_DIR / "pollen_stations.csv").read_text(encoding="utf-8")
        with open(FIXTURES_DIR / "pollen_data.json", encoding="utf-8") as f:
            cls.pollen_data = json.load(f)

    async def asyncSetUp(self):
        self.mock_session = MagicMock(spec=aiohttp.ClientSession)
        self.client = PollenClient(session=self.mock_session, language="en")

    async def test_get_pollen_station_list_pzh(self):
        """Test parsing pollen stations list including station PZH."""
        self.mock_session.get.return_value = make_mock_aiohttp_response(text=self.stations_csv)

        stations = await self.client.async_get_pollen_station_list()
        self.assertIsNotNone(stations)
        self.assertEqual(len(stations), 3)

        pzh = next((s for s in stations if s.abbreviation == "PZH"), None)
        self.assertIsNotNone(pzh)
        self.assertEqual(pzh.name, "Zürich-Flughafen")
        self.assertEqual(pzh.abbreviation, "PZH")
        self.assertEqual(pzh.type, "automated")
        self.assertEqual(pzh.altitude, 436.0)
        self.assertEqual(pzh.lat, 47.45)
        self.assertEqual(pzh.lng, 8.56)
        self.assertEqual(pzh.canton, "ZH")

    async def test_get_pollen_station_list_empty(self):
        """Test empty station list handling."""
        empty_csv = "station_name;station_abbr;station_type_de;station_type_fr;station_type_it;station_type_en;station_height_masl;station_coordinates_wgs84_lat;station_coordinates_wgs84_lon;station_canton\n"
        self.mock_session.get.return_value = make_mock_aiohttp_response(text=empty_csv)

        self.assertIsNone(await self.client.async_get_pollen_station_list())

    async def test_get_pollen_station_list_failure(self):
        """Test network failure when retrieving pollen station list."""
        self.mock_session.get.side_effect = aiohttp.ClientError("Connection failed")
        self.assertIsNone(await self.client.async_get_pollen_station_list())

    async def test_get_current_pollen_for_station_type_pzh(self):
        """Test retrieving individual pollen type measurement for station PZH."""
        self.mock_session.get.return_value = make_mock_aiohttp_response(json_data=self.pollen_data["birke"])

        value, timestamp = await self.client.async_get_current_pollen_for_station_type("PZH", "birke")
        self.assertEqual(value, 12.5)
        self.assertEqual(timestamp, datetime(2026, 10, 4, 8, 0, tzinfo=UTC))

    async def test_get_current_pollen_for_station_type_case_insensitive(self):
        """Test station matching is case-insensitive for pollen."""
        self.mock_session.get.return_value = make_mock_aiohttp_response(json_data=self.pollen_data["birke"])

        value, timestamp = await self.client.async_get_current_pollen_for_station_type("pzh", "birke")
        self.assertEqual(value, 12.5)
        self.assertIsNotNone(timestamp)

    async def test_get_current_pollen_for_station_type_not_found(self):
        """Test station not found in dataset."""
        self.mock_session.get.return_value = make_mock_aiohttp_response(json_data=self.pollen_data["birke"])

        value, timestamp = await self.client.async_get_current_pollen_for_station_type("UNKNOWN", "birke")
        self.assertIsNone(value)
        self.assertIsNone(timestamp)

    async def test_get_current_pollen_for_station_type_no_current(self):
        """Test station present but current data is null."""
        data = {"stations": [{"id": "PZH", "current": None}]}
        self.mock_session.get.return_value = make_mock_aiohttp_response(json_data=data)

        value, timestamp = await self.client.async_get_current_pollen_for_station_type("PZH", "birke")
        self.assertIsNone(value)
        self.assertIsNone(timestamp)

    async def test_get_current_pollen_for_station_type_http_error(self):
        """Test non-200 HTTP response."""
        self.mock_session.get.return_value = make_mock_aiohttp_response(status=500)

        value, timestamp = await self.client.async_get_current_pollen_for_station_type("PZH", "birke")
        self.assertIsNone(value)
        self.assertIsNone(timestamp)

    async def test_get_current_pollen_for_station_type_connection_error(self):
        """Test graceful error handling on client connection error."""
        self.mock_session.get.side_effect = aiohttp.ClientError("Timeout")

        value, timestamp = await self.client.async_get_current_pollen_for_station_type("PZH", "birke")
        self.assertIsNone(value)
        self.assertIsNone(timestamp)

    async def test_get_current_pollen_for_station_pzh_all_types(self):
        """Test get_current_pollen_for_station for PZH across all 7 monitored plant types."""
        def side_effect_get(url, *args, **kwargs):
            # Extract the key from URL (e.g. messwerte-pollen-birke-1h)
            for plant_key in self.pollen_data:
                if f"messwerte-pollen-{plant_key}-1h" in url:
                    return make_mock_aiohttp_response(json_data=self.pollen_data[plant_key])
            return make_mock_aiohttp_response(json_data={"stations": []})

        self.mock_session.get.side_effect = side_effect_get

        pollen = await self.client.async_get_current_pollen_for_station("PZH")
        self.assertIsNotNone(pollen)
        self.assertEqual(pollen.stationAbbr, "PZH")
        self.assertEqual(pollen.timestamp, datetime(2026, 10, 4, 8, 0, tzinfo=UTC))
        self.assertEqual(pollen.birch, (12.5, "p/m³"))
        self.assertEqual(pollen.grasses, (45.0, "p/m³"))
        self.assertEqual(pollen.alder, (0.0, "p/m³"))
        self.assertEqual(pollen.hazel, (5.0, "p/m³"))
        self.assertEqual(pollen.beech, (60.0, "p/m³"))
        self.assertEqual(pollen.ash, (150.0, "p/m³"))
        self.assertEqual(pollen.oak, (450.0, "p/m³"))

    async def test_get_current_pollen_all_none(self):
        """Test returning None when all pollen types return None."""
        self.client.async_get_current_pollen_for_station_type = AsyncMock(return_value=(None, None))
        pollen = await self.client.async_get_current_pollen_for_station("PZH")
        self.assertIsNone(pollen)

    async def test_get_pollen_station_list_http_error(self):
        """Test station list returns None on non-200 HTTP status."""
        self.mock_session.get.return_value = make_mock_aiohttp_response(status=500, text="Internal Server Error")
        self.assertIsNone(await self.client.async_get_pollen_station_list())

    async def test_get_pollen_station_list_timeout(self):
        """Test station list returns None on timeout."""
        self.mock_session.get.side_effect = TimeoutError("Timed out")
        self.assertIsNone(await self.client.async_get_pollen_station_list())

    async def test_get_pollen_station_list_corrupted_rows(self):
        """Test that station rows missing required headers are skipped."""
        csv_data = (
            "station_name;station_abbr;station_type_en;station_height_masl;station_coordinates_wgs84_lat;station_coordinates_wgs84_lon;station_canton\n"
            "Zürich-Flughafen;PZH;automated;436.0;47.45;8.56;ZH\n"
            ";;automated;500.0;47.0;8.0;ZH\n"  # missing name and abbr
            "Corrupted Row Missing Columns\n"
        )
        self.mock_session.get.return_value = make_mock_aiohttp_response(text=csv_data)
        stations = await self.client.async_get_pollen_station_list()
        self.assertIsNotNone(stations)
        self.assertEqual(len(stations), 1)
        self.assertEqual(stations[0].abbreviation, "PZH")

    async def test_get_current_pollen_for_station_type_broken_json(self):
        """Test broken JSON syntax raising json.JSONDecodeError is handled gracefully."""
        mock_ctx = make_mock_aiohttp_response(status=200)
        mock_resp = await mock_ctx.__aenter__()
        mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)
        self.mock_session.get.return_value = mock_ctx

        value, timestamp = await self.client.async_get_current_pollen_for_station_type("PZH", "birke")
        self.assertIsNone(value)
        self.assertIsNone(timestamp)

    async def test_get_current_pollen_for_station_type_timeout(self):
        """Test TimeoutError in pollen type fetch returns (None, None)."""
        self.mock_session.get.side_effect = TimeoutError("Timed out")
        value, timestamp = await self.client.async_get_current_pollen_for_station_type("PZH", "birke")
        self.assertIsNone(value)
        self.assertIsNone(timestamp)

    async def test_get_current_pollen_for_station_type_corrupted_structure(self):
        """Test corrupted JSON structures like stations not being a list."""
        data_not_list = {"stations": "corrupted_string_not_list"}
        self.mock_session.get.return_value = make_mock_aiohttp_response(json_data=data_not_list)
        value, timestamp = await self.client.async_get_current_pollen_for_station_type("PZH", "birke")
        self.assertIsNone(value)
        self.assertIsNone(timestamp)

        data_root_not_dict = "not_even_a_dict"
        self.mock_session.get.return_value = make_mock_aiohttp_response(json_data=data_root_not_dict)
        value, timestamp = await self.client.async_get_current_pollen_for_station_type("PZH", "birke")
        self.assertIsNone(value)
        self.assertIsNone(timestamp)

    async def test_get_current_pollen_for_station_type_corrupted_timestamp_skipped(self):
        """Test that a station entry with corrupted/missing timestamp is skipped as a datapoint."""
        # First entry for PZH has corrupted timestamp, second has valid timestamp
        data = {
            "stations": [
                {
                    "id": "PZH",
                    "current": {
                        "date": "invalid_date_epoch",
                        "value": 15.0,
                    }
                },
                {
                    "id": "PZH",
                    "current": {
                        "date": 1759564800000,
                        "value": 15.0,
                    }
                }
            ]
        }
        self.mock_session.get.return_value = make_mock_aiohttp_response(json_data=data)
        value, timestamp = await self.client.async_get_current_pollen_for_station_type("PZH", "birke")
        self.assertEqual(value, 15.0)
        self.assertEqual(timestamp, datetime(2025, 10, 4, 8, 0, tzinfo=UTC))

    async def test_get_current_pollen_for_station_type_missing_timestamp_skipped(self):
        """Test that an entry with null timestamp is skipped."""
        data = {
            "stations": [
                {
                    "id": "PZH",
                    "current": {
                        "date": None,
                        "value": 15.0,
                    }
                }
            ]
        }
        self.mock_session.get.return_value = make_mock_aiohttp_response(json_data=data)
        value, timestamp = await self.client.async_get_current_pollen_for_station_type("PZH", "birke")
        self.assertIsNone(value)
        self.assertIsNone(timestamp)

    async def test_get_current_pollen_for_station_type_corrupted_value(self):
        """Test that corrupted non-numeric pollen value converts to None."""
        data = {
            "stations": [
                {
                    "id": "PZH",
                    "current": {
                        "date": 1759564800000,
                        "value": "corrupted_non_numeric",
                    }
                }
            ]
        }
        self.mock_session.get.return_value = make_mock_aiohttp_response(json_data=data)
        value, timestamp = await self.client.async_get_current_pollen_for_station_type("PZH", "birke")
        self.assertIsNone(value)
        self.assertEqual(timestamp, datetime(2025, 10, 4, 8, 0, tzinfo=UTC))


if __name__ == "__main__":
    unittest.main()

