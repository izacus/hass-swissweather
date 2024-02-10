# MeteoSwiss integration for HASS

This is an integration to download data from MeteoSwiss and show current status, daily and hourly forecast in Home Assistant.

## Installation

1. Clone this repository in custom components:

```
git clone https://github.com/izacus/hass-swissweather.git swissweather
```

__Make sure directory name is `swissweather` or strings won't show up.__

2. Add swissweather integration to Home Assistant. You'll be asked for two pieces of information:

* Post Code: The post code of your location, used for forecast.
* Station code: The station code of weather station showing life data near you. The list of stations can be found in following [CSV][https://data.geo.admin.ch/ch.meteoschweiz.messnetz-automatisch/ch.meteoschweiz.messnetz-automatisch_en.csv] - use the WIGOS-ID of nearest station to you within reason (e.g. use Zurich-Fluntern "SMA" for Zurich city, not Uetliberg).