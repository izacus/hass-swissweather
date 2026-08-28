"""Tests for MeteoSwiss HTTP handling."""

import unittest
from unittest.mock import Mock, patch

from .module_loader import load_module


meteo = load_module("meteo")


class MeteoClientTest(unittest.TestCase):
    def setUp(self):
        self.client = meteo.MeteoClient()

    def test_forecast_request_has_timeout_and_checks_http_status(self):
        response = Mock()
        response.json.return_value = {"forecast": []}

        with patch.object(meteo.requests, "get", return_value=response) as get:
            result = self.client._get_forecast_json("8001", "en")

        self.assertEqual(result, {"forecast": []})
        get.assert_called_once()
        self.assertEqual(
            get.call_args.kwargs["timeout"], meteo.HTTP_TIMEOUT_SECONDS
        )
        response.raise_for_status.assert_called_once_with()

    def test_forecast_http_error_returns_none(self):
        response = Mock()
        response.raise_for_status.side_effect = meteo.requests.HTTPError("failed")

        with patch.object(meteo.requests, "get", return_value=response):
            result = self.client._get_forecast_json("8001", "en")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
