# MeteoSwiss integration for HASS

This is an integration to download data from [MeteoSwiss](https://www.meteoschweiz.admin.ch/#tab=forecast-map).

It currently supports:
  * Current weather state - temperature, precipitation, humidity, wind, etc. for a given autmated measurement station.
  * Hourly and daily weather forecast based on a location encoded with post number.

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=izacus&repository=hass-swissweather&category=integration)

### With HACS

1. Go to HACS page in Home Assistant
2. Click "three dots" in upper right corner and select "Custom Repositories..."
3. Enter `https://github.com/izacus/hass-swissweather` into "Repository" field
4. Select "Integration"
5. Click "Add"
6. On "Integrations" tab click "Explore And Download Repositories"
7. Enter "Swiss Weather" in search box and download the integration
8. Restart HASS

### Configure integration

1. Add Swiss Weather integration to Home Assistant. You'll be asked for two pieces of information:

* Post Code: The post code of your location, used for forecast - e.g. 8001 for Zurich.
* Station code: The station code of weather station showing live data near you. Choose the closest station within reason - e.g. it probably doesn't make sense to select "Uetliberg" to get data in Zurich due to altitude difference. Choose Kloten on Fluntern instead.
