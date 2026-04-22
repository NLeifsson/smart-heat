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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ZONES, CONF_ZONE_NAME, DOMAIN
from .coordinator import SmartHeatCoordinator, SmartHeatData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Heat sensor entities from a config entry."""
    coordinator: SmartHeatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = []

    # Outdoor temp mirror sensor
    entities.append(SmartHeatOutdoorTempSensor(coordinator, entry))

    # Per-zone sensors
    for zone_cfg in entry.data[CONF_ZONES]:
        zone_name = zone_cfg[CONF_ZONE_NAME]
        entities.extend([
            SmartHeatZoneTempSensor(coordinator, entry, zone_name),
            SmartHeatZoneDeltaTSensor(coordinator, entry, zone_name),
            SmartHeatZoneEnergySensor(coordinator, entry, zone_name),
            SmartHeatZoneClimateSensor(coordinator, entry, zone_name),
        ])

    # Per-zone analytics sensors (Phase 2)
    for zone_cfg in entry.data[CONF_ZONES]:
        zone_name = zone_cfg[CONF_ZONE_NAME]
        entities.extend([
            SmartHeatHeatLossScoreSensor(coordinator, entry, zone_name),
            SmartHeatEffectivenessSensor(coordinator, entry, zone_name),
        ])

    async_add_entities(entities)


class SmartHeatBaseSensor(CoordinatorEntity[SmartHeatCoordinator], SensorEntity):
    """Base class for Smart Heat sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmartHeatCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._entry = entry


# ── Outdoor temperature ─────────────────────────────────────────────


class SmartHeatOutdoorTempSensor(SmartHeatBaseSensor):
    """Mirrors the outdoor temperature for the dashboard."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: SmartHeatCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "outdoor_temp", "Outdoor Temperature")

    @callback
    def _handle_coordinator_update(self) -> None:
        data: SmartHeatData = self.coordinator.data
        self._attr_native_value = data.outdoor_temp
        self._attr_extra_state_attributes = {
            "stale": data.outdoor_sensor_stale,
        }
        self.async_write_ha_state()


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
            coordinator, entry, f"{zone_name}_indoor_temp", f"{zone_name} Indoor Temp"
        )
        self._zone_name = zone_name

    @callback
    def _handle_coordinator_update(self) -> None:
        data: SmartHeatData = self.coordinator.data
        zone = data.zones.get(self._zone_name)
        if zone:
            self._attr_native_value = (
                round(zone.indoor_temp_avg, 1) if zone.indoor_temp_avg is not None else None
            )
            self._attr_extra_state_attributes = {
                "sensor_count": len(zone.indoor_temps),
                "individual_temps": zone.indoor_temps,
                "stale": zone.sensors_stale,
            }
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


class SmartHeatZoneDeltaTSensor(SmartHeatBaseSensor):
    """Temperature difference: indoor avg − outdoor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: SmartHeatCoordinator, entry: ConfigEntry, zone_name: str
    ) -> None:
        super().__init__(
            coordinator, entry, f"{zone_name}_delta_t", f"{zone_name} ΔT"
        )
        self._zone_name = zone_name

    @callback
    def _handle_coordinator_update(self) -> None:
        data: SmartHeatData = self.coordinator.data
        zone = data.zones.get(self._zone_name)
        if zone and zone.indoor_temp_avg is not None and data.outdoor_temp is not None:
            self._attr_native_value = round(
                zone.indoor_temp_avg - data.outdoor_temp, 1
            )
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


class SmartHeatZoneEnergySensor(SmartHeatBaseSensor):
    """Energy consumption for a zone's heat pump."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self, coordinator: SmartHeatCoordinator, entry: ConfigEntry, zone_name: str
    ) -> None:
        super().__init__(
            coordinator, entry, f"{zone_name}_energy", f"{zone_name} Energy"
        )
        self._zone_name = zone_name

    @callback
    def _handle_coordinator_update(self) -> None:
        data: SmartHeatData = self.coordinator.data
        zone = data.zones.get(self._zone_name)
        if zone:
            self._attr_native_value = zone.energy_kwh
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


class SmartHeatZoneClimateSensor(SmartHeatBaseSensor):
    """Climate entity state + target temp for a zone."""

    _attr_icon = "mdi:thermostat"

    def __init__(
        self, coordinator: SmartHeatCoordinator, entry: ConfigEntry, zone_name: str
    ) -> None:
        super().__init__(
            coordinator, entry, f"{zone_name}_climate", f"{zone_name} Climate Status"
        )
        self._zone_name = zone_name

    @callback
    def _handle_coordinator_update(self) -> None:
        data: SmartHeatData = self.coordinator.data
        zone = data.zones.get(self._zone_name)
        if zone:
            self._attr_native_value = zone.climate_state
            self._attr_extra_state_attributes = {
                "current_temperature": zone.climate_current_temp,
                "target_temperature": zone.climate_target_temp,
                "climate_entity": zone.climate_entity,
            }
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


# ── Analytics sensors (Phase 2) ─────────────────────────────────────


class SmartHeatHeatLossScoreSensor(SmartHeatBaseSensor):
    """Relative heat-loss score for a zone. Lower = better insulated."""

    _attr_icon = "mdi:home-thermometer"
    _attr_native_unit_of_measurement = "W/°C"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: SmartHeatCoordinator, entry: ConfigEntry, zone_name: str
    ) -> None:
        super().__init__(
            coordinator, entry, f"{zone_name}_heat_loss", f"{zone_name} Heat Loss Score"
        )
        self._zone_name = zone_name
        self._score: float | None = None
        self._confidence: float | None = None

    def update_score(self, score: float | None, confidence: float | None) -> None:
        """Called by the analytics engine to update the score."""
        self._score = score
        self._confidence = confidence
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_native_value = self._score
        self._attr_extra_state_attributes = {
            "confidence": self._confidence,
            "unit_note": "Lower = better insulated. Relative metric, not a physical U-value.",
        }
        self.async_write_ha_state()


class SmartHeatEffectivenessSensor(SmartHeatBaseSensor):
    """Heating effectiveness: kWh per degree-hour. Lower = more efficient."""

    _attr_icon = "mdi:lightning-bolt-circle"
    _attr_native_unit_of_measurement = "kWh/°C·h"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: SmartHeatCoordinator, entry: ConfigEntry, zone_name: str
    ) -> None:
        super().__init__(
            coordinator, entry, f"{zone_name}_effectiveness", f"{zone_name} Heating Effectiveness"
        )
        self._zone_name = zone_name
        self._score: float | None = None
        self._confidence: float | None = None

    def update_score(self, score: float | None, confidence: float | None) -> None:
        """Called by the analytics engine to update the score."""
        self._score = score
        self._confidence = confidence
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_native_value = self._score
        self._attr_extra_state_attributes = {
            "confidence": self._confidence,
            "unit_note": "kWh consumed per degree-hour maintained. Lower = more efficient.",
        }
        self.async_write_ha_state()