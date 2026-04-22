"""Naming helpers for Swiss Weather entities and config entries."""

from __future__ import annotations


def format_station_display_name(
    name: str | None,
    canton: str | None = None,
    *,
    include_canton: bool = False,
) -> str | None:
    """Build a human-friendly display name for a station."""
    if name is None:
        return None

    cleaned = " ".join(name.split())
    if not cleaned:
        return None

    if "," in cleaned:
        base_name, _, trailing = cleaned.partition(",")
        canton_from_name = trailing.strip()
        if canton_from_name:
            return format_station_display_name(
                base_name,
                canton_from_name,
                include_canton=True,
            )

    if include_canton and canton:
        canton_clean = canton.strip()
        if canton_clean and not cleaned.casefold().endswith(canton_clean.casefold()):
            return f"{cleaned} {canton_clean}"
    return cleaned


def build_entry_title(
    forecast_name: str | None,
    station_name: str | None,
    pollen_name: str | None,
) -> str:
    """Build the config entry title."""
    parts = [part for part in (forecast_name, station_name, pollen_name) if part]
    if not parts:
        return "MeteoSwiss"
    return "MeteoSwiss " + " / ".join(parts)
