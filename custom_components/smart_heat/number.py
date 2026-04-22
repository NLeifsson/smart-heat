"""Number platform for Smart Heat — tunable comfort parameters."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_COMFORT_MAX,
    CONF_COMFORT_MIN,
    DEFAULT_COMFORT_MAX,
    DEFAULT_COMFORT_MIN,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Heat number entities."""
    async_add_entities([
        SmartHeatComfortNumber(
            entry,
            key="comfort_min",
            name="Comfort Minimum",
            default=entry.data.get(CONF_COMFORT_MIN, DEFAULT_COMFORT_MIN),
            min_val=10.0,
            max_val=25.0,
        ),
        SmartHeatComfortNumber(
            entry,
            key="comfort_max",
            name="Comfort Maximum",
            default=entry.data.get(CONF_COMFORT_MAX, DEFAULT_COMFORT_MAX),
            min_val=15.0,
            max_val=30.0,
        ),
    ])


class SmartHeatComfortNumber(NumberEntity, RestoreEntity):
    """Number entity for a comfort temperature parameter."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 0.5
    _attr_icon = "mdi:thermometer-lines"

    def __init__(
        self,
        entry: ConfigEntry,
        key: str,
        name: str,
        default: float,
        min_val: float,
        max_val: float,
    ) -> None:
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_native_value = default
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._default = default

    async def async_added_to_hass(self) -> None:
        """Restore previous value on restart."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            try:
                self._attr_native_value = float(last_state.state)
            except (ValueError, TypeError):
                pass

    async def async_set_native_value(self, value: float) -> None:
        """Set new comfort value."""
        self._attr_native_value = value
        self.async_write_ha_state()
