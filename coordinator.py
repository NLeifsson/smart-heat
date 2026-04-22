"""DataUpdateCoordinator for Smart Heat integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CLIMATE_ENTITY,
    CONF_ENERGY_SENSOR,
    CONF_INDOOR_TEMP_SENSORS,
    CONF_OUTDOOR_TEMP_SENSOR,
    CONF_ZONE_NAME,
    CONF_ZONES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    STALE_SENSOR_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

INVALID_STATES = {STATE_UNAVAILABLE, STATE_UNKNOWN, None}


@dataclass
class ZoneData:
    """Snapshot of a single zone's current state."""

    zone_name: str
    climate_entity: str
    indoor_temps: list[float] = field(default_factory=list)
    indoor_temp_avg: float | None = None
    climate_state: str | None = None
    climate_current_temp: float | None = None
    climate_target_temp: float | None = None
    energy_kwh: float | None = None
    sensors_stale: bool = False


@dataclass
class SmartHeatData:
    """Coordinator data — refreshed every scan interval."""

    outdoor_temp: float | None = None
    outdoor_sensor_stale: bool = False
    zones: dict[str, ZoneData] = field(default_factory=dict)


class SmartHeatCoordinator(DataUpdateCoordinator[SmartHeatData]):
    """Coordinator that polls all configured entities and builds a snapshot."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        self._outdoor_sensor: str = entry.data[CONF_OUTDOOR_TEMP_SENSOR]
        self._zones_config: list[dict[str, Any]] = entry.data[CONF_ZONES]

    # ── helpers ──────────────────────────────────────────────────────
    def _read_float(self, entity_id: str) -> float | None:
        """Read a float from an entity state, or None if unavailable."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in INVALID_STATES:
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    def _read_state(self, entity_id: str) -> str | None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in INVALID_STATES:
            return None
        return state.state

    def _read_attr_float(self, entity_id: str, attr: str) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        val = state.attributes.get(attr)
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    # ── main update ─────────────────────────────────────────────────
    async def _async_update_data(self) -> SmartHeatData:
        """Fetch data from all entities."""
        data = SmartHeatData()

        # Outdoor temperature
        data.outdoor_temp = self._read_float(self._outdoor_sensor)
        if data.outdoor_temp is None:
            data.outdoor_sensor_stale = True
            _LOGGER.warning("Outdoor sensor %s is unavailable", self._outdoor_sensor)

        # Per-zone data
        for zone_cfg in self._zones_config:
            zone_name = zone_cfg[CONF_ZONE_NAME]
            zd = ZoneData(
                zone_name=zone_name,
                climate_entity=zone_cfg[CONF_CLIMATE_ENTITY],
            )

            # Indoor temps — average of all configured sensors
            temps: list[float] = []
            for sensor_id in zone_cfg[CONF_INDOOR_TEMP_SENSORS]:
                val = self._read_float(sensor_id)
                if val is not None:
                    temps.append(val)
            zd.indoor_temps = temps
            zd.indoor_temp_avg = sum(temps) / len(temps) if temps else None

            if not temps:
                zd.sensors_stale = True
                _LOGGER.warning("Zone %s: no indoor temps available", zone_name)

            # Climate entity state
            zd.climate_state = self._read_state(zone_cfg[CONF_CLIMATE_ENTITY])
            zd.climate_current_temp = self._read_attr_float(
                zone_cfg[CONF_CLIMATE_ENTITY], "current_temperature"
            )
            zd.climate_target_temp = self._read_attr_float(
                zone_cfg[CONF_CLIMATE_ENTITY], "temperature"
            )

            # Energy sensor
            zd.energy_kwh = self._read_float(zone_cfg[CONF_ENERGY_SENSOR])

            data.zones[zone_name] = zd

        return data

    async def async_shutdown(self) -> None:
        """Clean up resources on unload."""
        _LOGGER.debug("SmartHeatCoordinator shutting down")
