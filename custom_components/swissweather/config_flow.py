"""Config flow for Swiss Weather integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util.location import distance

from .const import (
    CONF_FORECAST_NAME,
    CONF_POLLEN_STATION_CODE,
    CONF_POLLEN_STATION_NAME,
    CONF_POST_CODE,
    CONF_STATION_CODE,
    CONF_STATION_NAME,
    CONF_WEATHER_WARNINGS_NUMBER,
    DOMAIN,
)
from .forecast_points import (
    find_forecast_point_by_id,
    format_forecast_point_label,
    load_forecast_point_list,
    search_forecast_points,
)
from .naming import build_entry_title, format_station_display_name
from .station_lookup import (
    WeatherStation,
    find_station_by_code,
    load_pollen_station_list,
    load_weather_station_list,
    split_place_and_canton,
)

_LOGGER = logging.getLogger(__name__)

CONF_FORECAST_QUERY = "forecast_query"
CONF_FORECAST_POINT = "forecast_point"
SEARCH_AGAIN_OPTION = "__search_again__"
MAX_FORECAST_POINT_RESULTS = 50


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Swiss Weather."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow state."""
        self._pending_forecast_matches: list[Any] = []
        self._selected_forecast_point_id: str | None = None
        self._selected_forecast_name: str | None = None
        self._last_forecast_query: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial forecast search step."""
        if user_input is None:
            return await self._show_forecast_search_form("user")

        return await self._handle_forecast_search("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the forecast search step during reconfigure."""
        if user_input is None:
            return await self._show_forecast_search_form("reconfigure")

        self._abort_if_unique_id_mismatch()
        return await self._handle_forecast_search("reconfigure", user_input)

    async def async_step_forecast_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle forecast point confirmation/selection after a search."""
        if not self._pending_forecast_matches:
            return await self._show_forecast_search_form(self._active_step_id())

        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_FORECAST_POINT) == SEARCH_AGAIN_OPTION:
                self._pending_forecast_matches = []
                self._selected_forecast_point_id = None
                self._selected_forecast_name = None
                return await self._show_forecast_search_form(
                    self._active_step_id(),
                    user_input={CONF_FORECAST_QUERY: self._last_forecast_query},
                )

            selected_point = find_forecast_point_by_id(
                self._pending_forecast_matches, user_input.get(CONF_FORECAST_POINT)
            )
            if selected_point is not None:
                self._set_selected_forecast_point(selected_point.point_id, selected_point.display_name)
                return await self._show_details_form(self._active_step_id())
            errors[CONF_FORECAST_POINT] = "invalid_forecast_point"

        options = [
            SelectOptionDict(value=point.point_id, label=format_forecast_point_label(point))
            for point in self._pending_forecast_matches[:MAX_FORECAST_POINT_RESULTS]
        ]
        options.append(
            SelectOptionDict(value=SEARCH_AGAIN_OPTION, label="Search again")
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_FORECAST_POINT): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="forecast_pick",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle station, pollen, and warning selection."""
        if user_input is None:
            return await self._show_details_form(self._active_step_id())

        resolved_data = await self._augment_entry_data(user_input, self._selected_forecast_point_id)
        if self.source == config_entries.SOURCE_RECONFIGURE:
            reconfigure_entry = self._get_reconfigure_entry()
            return self.async_update_reload_and_abort(
                reconfigure_entry, data_updates=resolved_data
            )

        return self.async_create_entry(
            title=build_entry_title(
                resolved_data.get(CONF_FORECAST_NAME),
                resolved_data.get(CONF_STATION_NAME),
                resolved_data.get(CONF_POLLEN_STATION_NAME),
            ),
            data=resolved_data,
            description=f"{resolved_data[CONF_POST_CODE]}",
        )

    async def _show_forecast_search_form(
        self,
        origin_step: str,
        *,
        errors: dict[str, str] | None = None,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show the forecast search form."""
        default_query = self._last_forecast_query
        if origin_step == "reconfigure":
            reconfigure_entry = self._get_reconfigure_entry()
            if reconfigure_entry is not None:
                default_query = (
                    self._last_forecast_query
                    or reconfigure_entry.data.get(CONF_FORECAST_NAME)
                    or reconfigure_entry.data.get(CONF_POST_CODE, "")
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_FORECAST_QUERY,
                    default=(user_input or {}).get(CONF_FORECAST_QUERY, default_query),
                ): str
            }
        )
        return self.async_show_form(
            step_id=origin_step,
            data_schema=schema,
            errors=errors or {},
        )

    async def _show_details_form(
        self,
        origin_step: str,
        *,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show the second step with station and pollen options."""
        station_options = await self._get_weather_station_options()
        pollen_station_options = await self._get_pollen_station_options()

        existing_data: dict[str, Any] = {}
        if origin_step == "reconfigure":
            reconfigure_entry = self._get_reconfigure_entry()
            if reconfigure_entry is not None:
                existing_data = dict(reconfigure_entry.data)

        default_forecast_name = self._selected_forecast_name or existing_data.get(CONF_FORECAST_NAME, "")
        default_station_code = (user_input or {}).get(
            CONF_STATION_CODE, existing_data.get(CONF_STATION_CODE)
        )
        default_pollen_station_code = (user_input or {}).get(
            CONF_POLLEN_STATION_CODE, existing_data.get(CONF_POLLEN_STATION_CODE)
        )
        default_weather_warnings = (user_input or {}).get(
            CONF_WEATHER_WARNINGS_NUMBER,
            existing_data.get(CONF_WEATHER_WARNINGS_NUMBER, 1),
        )

        schema = vol.Schema(
            {
                vol.Optional(CONF_FORECAST_NAME, default=default_forecast_name): str,
                vol.Optional(CONF_STATION_CODE, default=default_station_code): SelectSelector(
                    SelectSelectorConfig(
                        options=station_options,
                        mode=SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional(
                    CONF_POLLEN_STATION_CODE,
                    default=default_pollen_station_code,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=pollen_station_options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_WEATHER_WARNINGS_NUMBER,
                    default=default_weather_warnings,
                ): NumberSelector(
                    NumberSelectorConfig(min=0, max=10, mode=NumberSelectorMode.BOX, step=1)
                ),
            }
        )
        return self.async_show_form(step_id="details", data_schema=schema)

    async def _handle_forecast_search(
        self, origin_step: str, user_input: dict[str, Any]
    ) -> ConfigFlowResult:
        """Search forecast points and route to the next step."""
        query = str(user_input.get(CONF_FORECAST_QUERY, "")).strip()
        self._last_forecast_query = query
        errors: dict[str, str] = {}

        if not query:
            errors[CONF_FORECAST_QUERY] = "forecast_query_required"
        elif not query.isdigit() and len(query) < 2:
            errors[CONF_FORECAST_QUERY] = "forecast_query_too_short"

        if errors:
            return await self._show_forecast_search_form(
                origin_step, errors=errors, user_input=user_input
            )

        forecast_points = await self.hass.async_add_executor_job(load_forecast_point_list)
        matches = search_forecast_points(forecast_points, query)
        if not matches:
            return await self._show_forecast_search_form(
                origin_step,
                errors={CONF_FORECAST_QUERY: "forecast_query_not_found"},
                user_input=user_input,
            )

        self._pending_forecast_matches = matches
        self._selected_forecast_point_id = None
        self._selected_forecast_name = None
        return await self.async_step_forecast_pick()

    def _set_selected_forecast_point(self, point_id: str, point_name: str) -> None:
        """Cache the selected forecast point between steps."""
        self._selected_forecast_point_id = str(point_id).strip()
        self._selected_forecast_name = point_name

    def _active_step_id(self) -> str:
        """Return the current top-level step origin."""
        if self.source == config_entries.SOURCE_RECONFIGURE:
            return "reconfigure"
        return "user"

    def format_station_name_for_dropdown(self, station: WeatherStation) -> str:
        """Format a weather/pollen station option for the dropdown."""
        station_distance = self._get_distance_to_station(station)
        if station_distance is None:
            return f"{station.name} ({station.canton})"
        return f"{station.name} ({station.canton}) - {station_distance / 1000:.0f} km away"

    async def _get_weather_station_options(self) -> list[SelectOptionDict]:
        """Load weather station options for the dropdown."""
        stations = await self.hass.async_add_executor_job(load_weather_station_list)
        if self.hass.config.latitude is not None and self.hass.config.longitude is not None:
            stations = sorted(stations, key=lambda item: self._get_distance_to_station(item))
        return [
            SelectOptionDict(value=station.code, label=self.format_station_name_for_dropdown(station))
            for station in stations
        ]

    async def _get_pollen_station_options(self) -> list[SelectOptionDict]:
        """Load pollen station options for the dropdown."""
        pollen_stations = await self.hass.async_add_executor_job(load_pollen_station_list)
        if self.hass.config.latitude is not None and self.hass.config.longitude is not None:
            pollen_stations = sorted(
                pollen_stations, key=lambda item: self._get_distance_to_station(item)
            )
        return [
            SelectOptionDict(value=station.code, label=self.format_station_name_for_dropdown(station))
            for station in pollen_stations
        ]

    def _get_distance_to_station(self, station: WeatherStation) -> float | None:
        """Return the distance from HA home location to a station."""
        h_lat = self.hass.config.latitude
        h_lng = self.hass.config.longitude
        if h_lat is None or h_lng is None:
            return None
        return distance(h_lat, h_lng, station.lat, station.lng)

    async def _augment_entry_data(
        self,
        user_input: dict[str, Any],
        selected_forecast_point_id: str | None = None,
    ) -> dict[str, Any]:
        """Attach resolved display names to the config entry data."""
        resolved_data = dict(user_input)
        post_code = selected_forecast_point_id or user_input.get(CONF_POST_CODE)
        if post_code is None:
            reconfigure_entry = self._get_reconfigure_entry()
            if reconfigure_entry is not None:
                post_code = reconfigure_entry.data.get(CONF_POST_CODE)
        resolved_data[CONF_POST_CODE] = str(post_code).strip() if post_code is not None else None

        forecast_name = user_input.get(CONF_FORECAST_NAME)
        if forecast_name is None:
            reconfigure_entry = self._get_reconfigure_entry()
            if reconfigure_entry is not None:
                forecast_name = reconfigure_entry.data.get(CONF_FORECAST_NAME)
        forecast_name = str(forecast_name).strip() if forecast_name is not None else ""

        forecast_points = await self.hass.async_add_executor_job(load_forecast_point_list)
        weather_stations = await self.hass.async_add_executor_job(load_weather_station_list)
        pollen_stations = await self.hass.async_add_executor_job(load_pollen_station_list)

        forecast_point = find_forecast_point_by_id(
            forecast_points, resolved_data.get(CONF_POST_CODE)
        )
        station = find_station_by_code(weather_stations, user_input.get(CONF_STATION_CODE))
        pollen_station = find_station_by_code(
            pollen_stations, user_input.get(CONF_POLLEN_STATION_CODE)
        )

        resolved_data[CONF_FORECAST_NAME] = (
            forecast_name
            or (forecast_point.display_name if forecast_point is not None else "")
            or self._selected_forecast_name
            or str(post_code).strip()
        )

        station_name, station_canton = split_place_and_canton(
            station.name if station is not None else None
        )
        resolved_data[CONF_STATION_NAME] = (
            format_station_display_name(
                station_name,
                station_canton or (station.canton if station is not None else None),
                include_canton=True,
            )
            if station is not None
            else None
        )
        resolved_data[CONF_POLLEN_STATION_NAME] = (
            format_station_display_name(pollen_station.name)
            if pollen_station is not None
            else None
        )
        resolved_data.pop(CONF_FORECAST_QUERY, None)
        resolved_data.pop(CONF_FORECAST_POINT, None)
        return resolved_data
