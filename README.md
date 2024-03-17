# MeteoSwiss integration for HASS

This is an integration to download data from MeteoSwiss and show current status, daily and hourly forecast in Home Assistant.

## Installation

### With HACS

1. Go to HACS page in Home Assistant
2. Click "three dots" in upper right corner and select "Custom Repositories..."
3. Enter `https://github.com/izacus/hass-swissweather` into "Repository" field
4. Select "Integration"
5. Click "Add"
6. On "Integrations" tab click "Explore And Download Repositories"
7. Enter "Swiss Weather" in search box and download the integration
8. Restart HASS

### Manually

1. Clone this repository in custom components:

```
git clone https://github.com/izacus/hass-swissweather.git swissweather
```

__Make sure directory name is `swissweather` or strings won't show up.__

2. Restart HASS

### Configure integration

1. Add Swiss Weather integration to Home Assistant. You'll be asked for two pieces of information:

* Post Code: The post code of your location, used for forecast.
* Station code: The station code of weather station showing live data near you. Choose the closest station within reason - e.g. it probably doesn't make sense to select "Uetliberg" to get data in Zurich due to altitude difference. Choose Kloten on Fluntern instead.
