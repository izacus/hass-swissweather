"""Tests for helper functions and data conversion in meteo.py and pollen.py."""
from pathlib import Path
import sys
import unittest

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from custom_components.swissweather.meteo import (
    StationInfo,
    to_float as meteo_to_float,
    to_int,
    to_meteoswiss_language,
)
from custom_components.swissweather.pollen import (
    PollenLevel,
    get_pollen_level,
    to_float as pollen_to_float,
)


class TestMeteoHelpers(unittest.TestCase):
    """Test standalone helper functions in meteo.py."""

    def test_to_meteoswiss_language(self):
        """Test language mapping for MeteoSwiss."""
        self.assertEqual(to_meteoswiss_language(None), "en")
        self.assertEqual(to_meteoswiss_language(""), "en")
        self.assertEqual(to_meteoswiss_language("de"), "de")
        self.assertEqual(to_meteoswiss_language("de-CH"), "de")
        self.assertEqual(to_meteoswiss_language("de_CH"), "de")
        self.assertEqual(to_meteoswiss_language("fr"), "fr")
        self.assertEqual(to_meteoswiss_language("fr-CH"), "fr")
        self.assertEqual(to_meteoswiss_language("it"), "it")
        self.assertEqual(to_meteoswiss_language("it-CH"), "it")
        self.assertEqual(to_meteoswiss_language("en"), "en")
        self.assertEqual(to_meteoswiss_language("en-US"), "en")
        # Unsupported languages fallback to English
        self.assertEqual(to_meteoswiss_language("pt-BR"), "en")
        self.assertEqual(to_meteoswiss_language("es"), "en")

    def test_to_float(self):
        """Test string to float conversions in meteo."""
        self.assertIsNone(meteo_to_float(None))
        self.assertIsNone(meteo_to_float("-"))
        self.assertIsNone(meteo_to_float("invalid"))
        self.assertEqual(meteo_to_float("16.00"), 16.0)
        self.assertEqual(meteo_to_float("-1.10"), -1.1)
        self.assertEqual(meteo_to_float("0.0"), 0.0)

    def test_to_int(self):
        """Test string to integer conversions in meteo."""
        self.assertIsNone(to_int(None))
        self.assertIsNone(to_int("-"))
        self.assertIsNone(to_int("not_a_number"))
        self.assertEqual(to_int("10"), 10)
        self.assertEqual(to_int("-5"), -5)
        self.assertEqual(to_int("0"), 0)

    def test_station_info_str(self):
        """Test string formatting of StationInfo."""
        info = StationInfo("Zürich / Fluntern", "SMA", "automated", 556.0, 47.38, 8.57, "ZH")
        self.assertIn("SMA", str(info))
        self.assertIn("Zürich / Fluntern", str(info))
        self.assertIn("ZH", str(info))


class TestPollenHelpers(unittest.TestCase):
    """Test pollen level classifications and helper functions in pollen.py."""

    def test_get_pollen_level_none_and_zero(self):
        """Test null and zero/negative pollen levels."""
        self.assertIsNone(get_pollen_level(None, "birch"))
        self.assertEqual(get_pollen_level(0.0, "birch"), PollenLevel.NONE)
        self.assertEqual(get_pollen_level(-1.0, "birch"), PollenLevel.NONE)

    def test_get_pollen_level_birch_thresholds(self):
        """Test birch specific classification thresholds: (10, 70, 300)."""
        self.assertEqual(get_pollen_level(5.0, "birch"), PollenLevel.LOW)
        self.assertEqual(get_pollen_level(10.0, "birch"), PollenLevel.LOW)
        self.assertEqual(get_pollen_level(11.0, "birch"), PollenLevel.MEDIUM)
        self.assertEqual(get_pollen_level(70.0, "birch"), PollenLevel.MEDIUM)
        self.assertEqual(get_pollen_level(71.0, "birch"), PollenLevel.STRONG)
        self.assertEqual(get_pollen_level(300.0, "birch"), PollenLevel.STRONG)
        self.assertEqual(get_pollen_level(301.0, "birch"), PollenLevel.VERY_STRONG)

    def test_get_pollen_level_grasses_thresholds(self):
        """Test grasses specific classification thresholds: (20, 50, 150)."""
        self.assertEqual(get_pollen_level(15.0, "grasses"), PollenLevel.LOW)
        self.assertEqual(get_pollen_level(20.0, "grasses"), PollenLevel.LOW)
        self.assertEqual(get_pollen_level(21.0, "grasses"), PollenLevel.MEDIUM)
        self.assertEqual(get_pollen_level(50.0, "grasses"), PollenLevel.MEDIUM)
        self.assertEqual(get_pollen_level(51.0, "grasses"), PollenLevel.STRONG)
        self.assertEqual(get_pollen_level(150.0, "grasses"), PollenLevel.STRONG)
        self.assertEqual(get_pollen_level(151.0, "grasses"), PollenLevel.VERY_STRONG)

    def test_get_pollen_level_other_plants(self):
        """Test other plant thresholds and default fallback."""
        # Oak / Beech: (50, 130, 400)
        self.assertEqual(get_pollen_level(45.0, "oak"), PollenLevel.LOW)
        self.assertEqual(get_pollen_level(100.0, "oak"), PollenLevel.MEDIUM)
        self.assertEqual(get_pollen_level(350.0, "oak"), PollenLevel.STRONG)
        self.assertEqual(get_pollen_level(405.0, "oak"), PollenLevel.VERY_STRONG)

        # Ash: (10, 100, 350)
        self.assertEqual(get_pollen_level(8.0, "ash"), PollenLevel.LOW)
        self.assertEqual(get_pollen_level(50.0, "ash"), PollenLevel.MEDIUM)
        self.assertEqual(get_pollen_level(200.0, "ash"), PollenLevel.STRONG)
        self.assertEqual(get_pollen_level(360.0, "ash"), PollenLevel.VERY_STRONG)

        # Unknown plant falls back to default thresholds (10, 70, 250)
        self.assertEqual(get_pollen_level(9.0, "unknown_plant"), PollenLevel.LOW)
        self.assertEqual(get_pollen_level(50.0, "unknown_plant"), PollenLevel.MEDIUM)
        self.assertEqual(get_pollen_level(100.0, "unknown_plant"), PollenLevel.STRONG)
        self.assertEqual(get_pollen_level(300.0, "unknown_plant"), PollenLevel.VERY_STRONG)

    def test_pollen_to_float(self):
        """Test string conversion to float in pollen module."""
        self.assertIsNone(pollen_to_float(None))
        self.assertIsNone(pollen_to_float("invalid"))
        self.assertEqual(pollen_to_float("12.5"), 12.5)
        self.assertEqual(pollen_to_float("0.0"), 0.0)


if __name__ == "__main__":
    unittest.main()
