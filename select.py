"""Select platform for Smart Heat — control mode selector."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONTROL_MODES, DOMAIN, MODE_OFF


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the control mode select entity."""
    async_add_entities([SmartHeatControlModeSelect(entry)])


class SmartHeatControlModeSelect(SelectEntity, RestoreEntity):
    """Select entity to choose the optimizer control mode."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:tune-vertical"
    _attr_options = CONTROL_MODES

    def __init__(self, entry: ConfigEntry) -> None:
        self._attr_unique_id = f"{entry.entry_id}_control_mode"
        self._attr_name = "Control Mode"
        self._attr_current_option = MODE_OFF

    async def async_added_to_hass(self) -> None:
        """Restore previous mode on restart."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in CONTROL_MODES:
            self._attr_current_option = last_state.state

    async def async_select_option(self, option: str) -> None:
        """Update the control mode."""
        self._attr_current_option = option
        self.async_write_ha_state()
