from dataclasses import dataclass
from datetime import UTC, datetime
import logging

from swiss_pollen import Measurement, Plant, PollenService, Station

from .meteo import FloatValue

logger = logging.getLogger(__name__)

@dataclass
class CurrentPollen(object):
    stationAbbr: str
    timestamp: datetime
    birch: FloatValue
    grasses: FloatValue
    alder: FloatValue
    hazel: FloatValue
    beech: FloatValue
    ash: FloatValue
    oak: FloatValue

def to_float(string: str) -> float | None:
    if string is None:
        return None

    try:
        return float(string)
    except ValueError:
        return None

class PollenClient(object):

    def get_current_pollen_for_station(self, stationAbbrev: str) -> CurrentPollen | None:
        logger.info("Loading data for %s...", stationAbbrev)
        try:
            current_values: dict[Station, list[Measurement]] = PollenService.current_values()
            station = next(s for s in current_values if s.code == stationAbbrev)
            if station is not None:
                value = current_values[station]
                date = next(v.date for v in value if v.date is not None)
                pollen = CurrentPollen(
                    station.code,
                    date.astimezone(UTC),
                    self._get_value_for_plant(value, Plant.BIRCH),
                    self._get_value_for_plant(value, Plant.GRASSES),
                    self._get_value_for_plant(value, Plant.ALDER),
                    self._get_value_for_plant(value, Plant.HAZEL),
                    self._get_value_for_plant(value, Plant.BEECH),
                    self._get_value_for_plant(value, Plant.ASH),
                    self._get_value_for_plant(value, Plant.OAK),
                )
                logger.debug("Current pollen: %s", pollen)
                return pollen
        except Exception as e:
            logger.exception("Failed to load pollen data.")
        return None

    @staticmethod
    def _get_value_for_plant(current_values_for_station: list[Measurement], plant: Plant) -> FloatValue | None:
        try:
            value = next(v.value for v in current_values_for_station if v.plant == plant)
            return value, "p/m3"
        except:
            return None