"""Tests for station handling in the config flow."""
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from custom_components.swissweather.config_flow import (
    GROUP_STATIONS_SECTION,
    ConfigFlow,
    WeatherStation,
    get_reporting_stations,
    merge_reconfigure_input,
    validate_group_stations,
)
from custom_components.swissweather.meteo import MeteoClient
from tests.test_meteo import FIXTURES_DIR, make_mock_aiohttp_response

STATION_LIST = """Station;Abbr.;Station type;Station height m a. sea level;Latitude;Longitude;Canton;Measurements
Zürich / Fluntern;SMA;Weather station;556;47.377925;8.565742;ZH;Temperature, Humidity, Dew point, Precipitation, Pressure, Wind, Global radiation, Sunshine
Zürich / Kloten;KLO;Weather station;426;47.479558;8.536079;ZH;Wind, Pressure
Zürich / Affoltern;REH;Precipitation station;444;47.427705;8.517891;ZH;Precipitation
"""


class TestMergeReconfigureInput(unittest.TestCase):
    """Test how reconfigure input is stored in the entry data."""

    def test_section_is_flattened(self):
        """Test group stations from the section end up as top-level keys."""
        data = merge_reconfigure_input(
            {"postCode": "8001", "stationCode": "SMA"},
            {"stationCode": "SMA", GROUP_STATIONS_SECTION: {"windStationCode": "KLO"}})
        self.assertEqual(data, {"postCode": "8001", "stationCode": "SMA", "windStationCode": "KLO"})

    def test_cleared_station_is_removed(self):
        """Test a group station missing from the section is removed from the data."""
        data = merge_reconfigure_input(
            {"postCode": "8001", "stationCode": "SMA", "windStationCode": "KLO", "pressureStationCode": "KLO"},
            {"stationCode": "SMA", GROUP_STATIONS_SECTION: {"pressureStationCode": "KLO"}})
        self.assertEqual(data, {"postCode": "8001", "stationCode": "SMA", "pressureStationCode": "KLO"})


class TestStationOptions(unittest.IsolatedAsyncioTestCase):
    """Test loading and filtering of the station list."""

    async def asyncSetUp(self):
        self.flow = ConfigFlow()
        self.flow.hass = MagicMock()
        self.flow.hass.config.latitude = None
        self.flow.hass.config.longitude = None
        session = MagicMock()
        session.get.return_value = make_mock_aiohttp_response(text=STATION_LIST)
        with patch("custom_components.swissweather.config_flow.async_get_clientsession", return_value=session):
            self.stations = await self.flow.async_load_station_list()

    def test_precipitation_stations_are_skipped(self):
        """Test only stations reporting current data are loaded."""
        self.assertEqual([station.code for station in self.stations], ["SMA", "KLO"])
        self.assertEqual(self.stations[1].measurements, ["Wind", "Pressure"])

    def test_options_filtered_by_measurement(self):
        """Test dropdowns only list stations measuring that group."""
        def codes(measurement):
            return [option["value"] for option in self.flow._get_weather_station_options(self.stations, measurement)]
        self.assertEqual(codes("Temperature"), ["SMA"])
        self.assertEqual(codes("Wind"), ["SMA", "KLO"])
        self.assertEqual(codes("Sunshine"), ["SMA"])

    def test_group_options_use_names(self):
        """Test the searchable pickers get station names as values."""
        options = self.flow._get_weather_station_options(self.stations, "Wind", use_names=True)
        self.assertEqual([option["value"] for option in options], ["Zürich / Fluntern", "Zürich / Kloten"])


class TestGroupStationsAgainstCurrentData(unittest.IsolatedAsyncioTestCase):
    """Test that group stations are offered and accepted only if they report values."""

    STATIONS = [
        WeatherStation("Zürich / Fluntern", "SMA", 556, 47.38, 8.57, "ZH", ["Temperature", "Precipitation", "Wind"]),
        WeatherStation("Jungfraujoch", "JUN", 3571, 46.55, 7.98, "BE", ["Temperature", "Precipitation", "Wind"]),
    ]

    async def asyncSetUp(self):
        session = MagicMock()
        session.get.return_value = make_mock_aiohttp_response(
            text=(FIXTURES_DIR / "vqha80_sample.csv").read_text(encoding="utf-8"))
        self.current_weather = await MeteoClient(session).async_get_current_weather_for_all_stations()

    def test_reporting_stations(self):
        """Test only stations with a current value for the group are offered (JUN has no precipitation)."""
        def codes(group):
            return [station.code for station in get_reporting_stations(self.STATIONS, self.current_weather, group)]
        self.assertEqual(codes("wind"), ["SMA", "JUN"])
        self.assertEqual(codes("precipitation"), ["SMA"])
        self.assertEqual(len(get_reporting_stations(self.STATIONS, None, "precipitation")), 2)

    def test_name_or_code_is_saved_as_code(self):
        """Test picked names and typed codes or names are stored as station codes."""
        data = {"stationCode": "SMA", "windStationCode": "Jungfraujoch", "temperatureStationCode": " jun "}
        self.assertEqual(validate_group_stations(data, self.STATIONS, self.current_weather), ({}, {}))
        self.assertEqual(data, {"stationCode": "SMA", "windStationCode": "JUN", "temperatureStationCode": "JUN"})

    def test_no_group_stations(self):
        """Test entries without group stations don't need current data."""
        self.assertEqual(validate_group_stations({"stationCode": "SMA"}, self.STATIONS, None), ({}, {}))

    def test_unknown_station_is_rejected(self):
        """Test typed text that is neither a station code nor a name is rejected."""
        self.assertEqual(validate_group_stations({"windStationCode": "Kloten"}, self.STATIONS, self.current_weather),
                         ({"base": "unknown_group_station"}, {"station": "Kloten"}))

    def test_station_without_values_is_rejected(self):
        """Test a typed station without values for the group is rejected."""
        self.assertEqual(validate_group_stations({"precipitationStationCode": "JUN"}, self.STATIONS, self.current_weather),
                         ({"base": "no_group_values"}, {"station": "Jungfraujoch", "group": "precipitation"}))

    def test_missing_current_data(self):
        """Test group stations can't be checked without current data."""
        self.assertEqual(validate_group_stations({"windStationCode": "SMA"}, self.STATIONS, None),
                         ({"base": "cannot_connect"}, {}))


class TestReconfigureForm(unittest.IsolatedAsyncioTestCase):
    """Test the reconfigure form itself."""

    async def test_accepts_entry_without_pollen_station(self):
        """Test the form validates when no pollen station is chosen."""
        vqha80 = (FIXTURES_DIR / "vqha80_sample.csv").read_text(encoding="utf-8")
        session = MagicMock()
        session.get.side_effect = lambda url, **kwargs: make_mock_aiohttp_response(
            text=vqha80 if "VQHA80" in url else STATION_LIST)
        flow = ConfigFlow()
        flow.hass = MagicMock()
        flow.hass.config.latitude = None
        flow.hass.config.longitude = None
        flow._get_reconfigure_entry = MagicMock(return_value=MagicMock(data={"postCode": "8001", "stationCode": "SMA"}))
        flow._get_pollen_station_options = AsyncMock(return_value=[])
        with patch("custom_components.swissweather.config_flow.async_get_clientsession", return_value=session):
            result = await flow.async_step_reconfigure()
        user_input = {"stationCode": "SMA", "weatherWarningsNumber": 1, GROUP_STATIONS_SECTION: {}}
        self.assertEqual(result["data_schema"](user_input), {**user_input, "weatherWarningsNumber": 1.0})
