"""Sensor platform for Smart Heat — read-only calculated sensors."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ZONES, CONF_ZONE_NAME, DOMAIN
from .coordinator import SmartHeatCoordinator, SmartHeatData, ZoneData

_LOGGER = logging.getLogger(__name__)


def _zone_device_info(entry: ConfigEntry, zone_name: str) -> DeviceInfo:
    """Build DeviceInfo for a zone — groups all zone sensors under one device."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{zone_name}")},
        name=f"Smart Heat — {zone_name}",
        manufacturer="Smart Heat",
        model="Heating Zone",
        entry_type=DeviceEntryType.SERVICE,
        via_device=(DOMAIN, entry.entry_id),
    )


def _hub_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Build DeviceInfo for the main Smart Heat hub device."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Smart Heat",
        manufacturer="Smart Heat",
        model="Controller",
        entry_type=DeviceEntryType.SERVICE,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Heat sensor entities from a config entry."""
    coordinator: SmartHeatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = []

    # Outdoor temp sensor
    entities.append(SmartHeatOutdoorTempSensor(coordinator, entry))

    # Per-zone sensors
    for zone_cfg in entry.data[CONF_ZONES]:
        zone_name = zone_cfg[CONF_ZONE_NAME]
        entities.extend([
            SmartHeatZoneTempSensor(coordinator, entry, zone_name),
            SmartHeatZoneDeltaTSensor(coordinator, entry, zone_name),
            SmartHeatZoneEnergySensor(coordinator, entry, zone_name),
            SmartHeatZoneClimateSensor(coordinator, entry, zone_name),
            SmartHeatHeatLossScoreSensor(coordinator, entry, zone_name),
            SmartHeatEffectivenessSensor(coordinator, entry, zone_name),
        ])

    async_add_entities(entities)


# ── Helpers ─────────────────────────────────────────────────────────

class SmartHeatBaseSensor(CoordinatorEntity[SmartHeatCoordinator], SensorEntity):
    """Base class for Smart Heat sensors using @property pattern."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmartHeatCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        device_info: DeviceInfo | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = device_info or _hub_device_info(entry)
        self._entry = entry

    @property
    def _data(self) -> SmartHeatData | None:
        """Shortcut to coordinator data."""
        return self.coordinator.data

    def _get_zone(self, zone_name: str) -> ZoneData | None:
        """Get zone data safely."""
        data = self._data
        if data is None:
            return None
        return data.zones.get(zone_name)


# ── Outdoor temperature ─────────────────────────────────────────────


class SmartHeatOutdoorTempSensor(SmartHeatBaseSensor):
    """Mirrors the outdoor temperature."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: SmartHeatCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "outdoor_temp", "Outdoor Temperature")

    @property
    def native_value(self) -> float | None:
        data = self._data
        return data.outdoor_temp if data else None

    @property
    def extra_state_attributes(self) -> dict | None:
        data = self._data
        if data is None:
            return None
        return {"stale": data.outdoor_sensor_stale}


# ── Per-zone sensors ────────────────────────────────────────────────


class SmartHeatZoneTempSensor(SmartHeatBaseSensor):
    """Average indoor temperature for a zone."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: SmartHeatCoordinator, entry: ConfigEntry, zone_name: str
    ) -> None:
        super().__init__(
            coordinator, entry, f"{zone_name}_indoor_temp", f"{zone_name} Indoor Temp",
            device_info=_zone_device_info(entry, zone_name),
        )
        self._zone_name = zone_name

    @property
    def native_value(self) -> float | None:
        zone = self._get_zone(self._zone_name)
        if zone and zone.indoor_temp_avg is not None:
            return round(zone.indoor_temp_avg, 1)
        return None

    @property
    def extra_state_attributes(self) -> dict | None:
        zone = self._get_zone(self._zone_name)
        if zone is None:
            return None
        return {
            "sensor_count": len(zone.indoor_temps),
            "individual_temps": zone.indoor_temps,
            "stale": zone.sensors_stale,
        }


class SmartHeatZoneDeltaTSensor(SmartHeatBaseSensor):
    """Temperature difference: indoor avg − outdoor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: SmartHeatCoordinator, entry: ConfigEntry, zone_name: str
    ) -> None:
        super().__init__(
            coordinator, entry, f"{zone_name}_delta_t", f"{zone_name} ΔT",
            device_info=_zone_device_info(entry, zone_name),
        )
        self._zone_name = zone_name

    @property
    def native_value(self) -> float | None:
        data = self._data
        zone = self._get_zone(self._zone_name)
        if zone and zone.indoor_temp_avg is not None and data and data.outdoor_temp is not None:
            return round(zone.indoor_temp_avg - data.outdoor_temp, 1)
        return None


class SmartHeatZoneEnergySensor(SmartHeatBaseSensor):
    """Energy consumption for a zone's heat pump."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self, coordinator: SmartHeatCoordinator, entry: ConfigEntry, zone_name: str
    ) -> None:
        super().__init__(
            coordinator, entry, f"{zone_name}_energy", f"{zone_name} Energy",
            device_info=_zone_device_info(entry, zone_name),
        )
        self._zone_name = zone_name

    @property
    def native_value(self) -> float | None:
        zone = self._get_zone(self._zone_name)
        return zone.energy_kwh if zone else None


class SmartHeatZoneClimateSensor(SmartHeatBaseSensor):
    """Climate entity state + target temp for a zone."""

    _attr_icon = "mdi:thermostat"

    def __init__(
        self, coordinator: SmartHeatCoordinator, entry: ConfigEntry, zone_name: str
    ) -> None:
        super().__init__(
            coordinator, entry, f"{zone_name}_climate", f"{zone_name} Climate Status",
            device_info=_zone_device_info(entry, zone_name),
        )
        self._zone_name = zone_name

    @property
    def native_value(self) -> str | None:
        zone = self._get_zone(self._zone_name)
        return zone.climate_state if zone else None

    @property
    def extra_state_attributes(self) -> dict | None:
        zone = self._get_zone(self._zone_name)
        if zone is None:
            return None
        return {
            "current_temperature": zone.climate_current_temp,
            "target_temperature": zone.climate_target_temp,
            "climate_entity": zone.climate_entity,
        }


# ── Analytics sensors ───────────────────────────────────────────────


class SmartHeatHeatLossScoreSensor(SmartHeatBaseSensor):
    """Relative heat-loss score for a zone. Lower = better insulated."""

    _attr_icon = "mdi:home-thermometer"
    _attr_native_unit_of_measurement = "W/°C"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: SmartHeatCoordinator, entry: ConfigEntry, zone_name: str
    ) -> None:
        super().__init__(
            coordinator, entry, f"{zone_name}_heat_loss", f"{zone_name} Heat Loss Score",
            device_info=_zone_device_info(entry, zone_name),
        )
        self._zone_name = zone_name
        self._score: float | None = None
        self._confidence: float | None = None

    def update_score(self, score: float | None, confidence: float | None) -> None:
        """Called by the analytics engine to update the score."""
        self._score = score
        self._confidence = confidence
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        return self._score

    @property
    def extra_state_attributes(self) -> dict | None:
        return {
            "confidence": self._confidence,
            "unit_note": "Lower = better insulated. Relative metric, not a physical U-value.",
        }


class SmartHeatEffectivenessSensor(SmartHeatBaseSensor):
    """Heating effectiveness: kWh per degree-hour. Lower = more efficient."""

    _attr_icon = "mdi:lightning-bolt-circle"
    _attr_native_unit_of_measurement = "kWh/°C·h"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: SmartHeatCoordinator, entry: ConfigEntry, zone_name: str
    ) -> None:
        super().__init__(
            coordinator, entry, f"{zone_name}_effectiveness", f"{zone_name} Heating Effectiveness",
            device_info=_zone_device_info(entry, zone_name),
        )
        self._zone_name = zone_name
        self._score: float | None = None
        self._confidence: float | None = None

    def update_score(self, score: float | None, confidence: float | None) -> None:
        """Called by the analytics engine to update the score."""
        self._score = score
        self._confidence = confidence
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        return self._score

    @property
    def extra_state_attributes(self) -> dict | None:
        return {
            "confidence": self._confidence,
            "unit_note": "kWh consumed per degree-hour maintained. Lower = more efficient.",
        }