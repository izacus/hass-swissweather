# MeteoSwiss integration for HASS

This is an integration to download data from [MeteoSwiss](https://www.meteoschweiz.admin.ch/#tab=forecast-map).

It currently supports:
  * Current weather state - temperature, precipitation, humidity, wind, etc. for a given autmated measurement station.
  * Hourly and daily weather forecast based on a location encoded with post nurmber.
  * Weather warnings (e.g. floods, fires, earthquake dangers, etc.) for the set location.
  * Pollen measurement status across a set of automated stations.

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

Add Swiss Weather integration to Home Assistant. You'll be asked for a few pieces of information:

* **Post Code**: The post code of your location, used for forecast and weather alerts - e.g. 8001 for Zurich.
* **Station code**: The station code of weather station measuring live data near you. Choose the closest station within reason - e.g. it probably doesn't make sense to select "Uetliberg" to get data in Zurich due to altitude difference. Choose Kloten on Fluntern instead. If not set, limited data will be pulled from the forecast.
* **Pollen station code**: The station code of pollen measurement station for pollen data. Same rules apply as before.
* **Number of weather warning entities**: This sets the number of separate entities created for weather warnings. By default is one - entities are created only for the most severe weather warning. You can increase this to create separate entities for 2nd most severe, 3rd, etc.

### Example Weather Alert mushroom card

Data for weather alert needs to be pulled out of a card. Example mushroom template card which shows most severe weather alert and a badge for more:

```
type: custom:mushroom-template-card
icon: mdi:alert
primary: " {{states('sensor.most_severe_weather_warning_at_8000') }} - {{states('sensor.most_severe_weather_warning_level_at_8000')}}"
secondary: "{{state_attr('sensor.most_severe_weather_alert_at_8000', 'text')}}"
icon_color: >
  {{ state_attr('sensor.most_severe_weather_warning_level_at_8134','icon_color') }}
badge_color: red
badge_icon: |
  {% set number_of_warnings=states("sensor.weather_warnings_at_8000") |int %}
  {% if number_of_warnings > 9 %}
    mdi:numeric-9-plus
  {% elif number_of_warnings > 1 and number_of_warnings < 10 %}
    mdi:numeric-{{number_of_warnings}}
  {% endif %}
multiline_secondary: true
tap_action:
  action: more-info
  entity: sensor.most_severe_weather_alert_at_8000
visibility:
  - condition: state
    entity: sensor.most_severe_weather_alert_at_8000
    state_not: unavailable 
```
