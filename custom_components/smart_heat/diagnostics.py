"""Diagnostics support for Smart Heat integration.

Provides a downloadable snapshot of all current data from
Settings → Devices & Services → Smart Heat → ⋮ → Download diagnostics.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ZONES, CONF_ZONE_NAME, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not entry_data:
        return {"error": "Integration not loaded"}

    coordinator = entry_data.get("coordinator")
    database = entry_data.get("database")

    result: dict[str, Any] = {
        "config": {
            "zones": [
                {
                    "zone_name": z.get(CONF_ZONE_NAME),
                    "climate_entity": z.get("climate_entity"),
                    "indoor_sensors": z.get("indoor_temp_sensors"),
                    "energy_sensor": z.get("energy_sensor"),
                    "floor_area": z.get("floor_area"),
                }
                for z in entry.data.get(CONF_ZONES, [])
            ],
            "outdoor_sensor": entry.data.get("outdoor_temp_sensor"),
            "comfort_min": entry.data.get("comfort_min"),
            "comfort_max": entry.data.get("comfort_max"),
        },
    }

    # Current coordinator data
    if coordinator and coordinator.data:
        data = coordinator.data
        result["current_state"] = {
            "outdoor_temp": data.outdoor_temp,
            "outdoor_stale": data.outdoor_sensor_stale,
            "zones": {},
        }
        for zone_name, zone in data.zones.items():
            result["current_state"]["zones"][zone_name] = {
                "indoor_temp_avg": zone.indoor_temp_avg,
                "indoor_temps": zone.indoor_temps,
                "climate_state": zone.climate_state,
                "climate_current_temp": zone.climate_current_temp,
                "climate_target_temp": zone.climate_target_temp,
                "energy_kwh": zone.energy_kwh,
                "sensors_stale": zone.sensors_stale,
            }

    # Recent optimizer decisions from database
    if database:
        try:
            result["recent_decisions"] = {}
            for zone_cfg in entry.data.get(CONF_ZONES, []):
                zone_name = zone_cfg[CONF_ZONE_NAME]
                snapshots = await database.get_recent_snapshots(zone_name, hours=24)
                result["recent_decisions"][zone_name] = {
                    "snapshots_24h": len(snapshots),
                    "latest_snapshots": snapshots[-5:] if snapshots else [],
                }
        except Exception as exc:
            result["recent_decisions"] = {"error": str(exc)}

    return result
