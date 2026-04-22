"""Smart Heat integration — setup and teardown."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)

SmartHeatConfigEntry = ConfigEntry

DATA_COORDINATOR = "coordinator"
DATA_DATABASE = "database"
DATA_CONTROLLER = "controller"


async def async_setup_entry(hass: HomeAssistant, entry: SmartHeatConfigEntry) -> bool:
    """Set up Smart Heat from a config entry."""
    # Lazy imports — aiosqlite may not be available until HA installs requirements
    from .controller import SmartHeatController
    from .coordinator import SmartHeatCoordinator
    from .database import SmartHeatDatabase

    # Database
    db_path = Path(hass.config.path("smart_heat", f"{entry.entry_id}.db"))
    database = SmartHeatDatabase(db_path)
    await database.async_setup()

    # Coordinator
    coordinator = SmartHeatCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    # Controller
    controller = SmartHeatController(hass, coordinator, database, entry)
    await controller.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_DATABASE: database,
        DATA_CONTROLLER: controller,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("Smart Heat integration loaded for entry %s", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SmartHeatConfigEntry) -> bool:
    """Unload a config entry."""
    from .controller import SmartHeatController
    from .coordinator import SmartHeatCoordinator
    from .database import SmartHeatDatabase

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id)
        controller: SmartHeatController = entry_data[DATA_CONTROLLER]
        database: SmartHeatDatabase = entry_data[DATA_DATABASE]
        coordinator: SmartHeatCoordinator = entry_data[DATA_COORDINATOR]
        await controller.async_stop()
        await coordinator.async_shutdown()
        await database.async_close()
        _LOGGER.info("Smart Heat integration unloaded for entry %s", entry.entry_id)
    return unload_ok
