"""Tests for the MeteoSwiss Open Data pollen client."""

from datetime import UTC, datetime
import unittest
from unittest.mock import Mock, patch

from .module_loader import load_module


load_module("meteo")
pollen = load_module("pollen")


POLLEN_CSV = b"""station_abbr;reference_timestamp;kabetuh0;khpoach0;kaalnuh0;kacoryh0;kafaguh0;kafraxh0;kaquerh0
PZH;28.08.2026 02:00;1;2;3;4;5;6;7
PZH;28.08.2026 03:00;10;20;30;40;50;60;70
"""


class PollenClientTest(unittest.TestCase):
    def test_loads_all_pollen_values_with_one_request(self):
        response = Mock()
        response.content = POLLEN_CSV

        with patch.object(pollen.requests, "get", return_value=response) as get:
            result = pollen.PollenClient().get_current_pollen_for_station("PZH")

        self.assertIsNotNone(result)
        self.assertEqual(result.timestamp, datetime(2026, 8, 28, 3, tzinfo=UTC))
        self.assertEqual(result.birch, (10.0, "p/m³"))
        self.assertEqual(result.grasses, (20.0, "p/m³"))
        self.assertEqual(result.alder, (30.0, "p/m³"))
        self.assertEqual(result.hazel, (40.0, "p/m³"))
        self.assertEqual(result.beech, (50.0, "p/m³"))
        self.assertEqual(result.ash, (60.0, "p/m³"))
        self.assertEqual(result.oak, (70.0, "p/m³"))
        get.assert_called_once_with(
            "https://data.geo.admin.ch/ch.meteoschweiz.ogd-pollen/pzh/ogd-pollen_pzh_h_now.csv",
            timeout=pollen.HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
