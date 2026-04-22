"""Config flow for Smart Heat integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CLIMATE_ENTITY,
    CONF_COMFORT_MAX,
    CONF_COMFORT_MIN,
    CONF_ENERGY_SENSOR,
    CONF_FLOOR_AREA,
    CONF_INDOOR_TEMP_SENSORS,
    CONF_OUTDOOR_TEMP_SENSOR,
    CONF_ZONE_NAME,
    CONF_ZONES,
    DEFAULT_COMFORT_MAX,
    DEFAULT_COMFORT_MIN,
    DEFAULT_FLOOR_AREA,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SmartHeatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Heat."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._zones: list[dict[str, Any]] = []
        self._outdoor_sensor: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step — outdoor sensor selection."""
        if user_input is not None:
            self._outdoor_sensor = user_input[CONF_OUTDOOR_TEMP_SENSOR]
            return await self.async_step_zone()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_OUTDOOR_TEMP_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=SENSOR_DOMAIN,
                            device_class="temperature",
                        )
                    ),
                }
            ),
            description_placeholders={"step": "1/3"},
        )

    async def async_step_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle adding a zone (heat pump + sensors)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            zone = {
                CONF_ZONE_NAME: user_input[CONF_ZONE_NAME],
                CONF_CLIMATE_ENTITY: user_input[CONF_CLIMATE_ENTITY],
                CONF_INDOOR_TEMP_SENSORS: user_input[CONF_INDOOR_TEMP_SENSORS],
                CONF_ENERGY_SENSOR: user_input[CONF_ENERGY_SENSOR],
                CONF_FLOOR_AREA: user_input.get(CONF_FLOOR_AREA, DEFAULT_FLOOR_AREA),
            }
            self._zones.append(zone)
            return await self.async_step_add_more()

        return self.async_show_form(
            step_id="zone",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ZONE_NAME): str,
                    vol.Required(CONF_CLIMATE_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=CLIMATE_DOMAIN)
                    ),
                    vol.Required(CONF_INDOOR_TEMP_SENSORS): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=SENSOR_DOMAIN,
                            device_class="temperature",
                            multiple=True,
                        )
                    ),
                    vol.Required(CONF_ENERGY_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=SENSOR_DOMAIN,
                            device_class="energy",
                        )
                    ),
                    vol.Optional(
                        CONF_FLOOR_AREA, default=DEFAULT_FLOOR_AREA
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0, max=10000, step=1, unit_of_measurement="m²",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"zone_count": str(len(self._zones) + 1)},
        )

    async def async_step_add_more(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask if user wants to add another zone."""
        if user_input is not None:
            if user_input.get("add_another"):
                return await self.async_step_zone()
            return await self.async_step_comfort()

        return self.async_show_form(
            step_id="add_more",
            data_schema=vol.Schema(
                {
                    vol.Required("add_another", default=False): bool,
                }
            ),
            description_placeholders={
                "zone_count": str(len(self._zones)),
            },
        )

    async def async_step_comfort(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure comfort ranges."""
        if user_input is not None:
            data = {
                CONF_OUTDOOR_TEMP_SENSOR: self._outdoor_sensor,
                CONF_ZONES: self._zones,
                CONF_COMFORT_MIN: user_input[CONF_COMFORT_MIN],
                CONF_COMFORT_MAX: user_input[CONF_COMFORT_MAX],
            }
            zone_names = ", ".join(z[CONF_ZONE_NAME] for z in self._zones)
            return self.async_create_entry(
                title=f"Smart Heat ({zone_names})",
                data=data,
            )

        return self.async_show_form(
            step_id="comfort",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_COMFORT_MIN, default=DEFAULT_COMFORT_MIN
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=10, max=30, step=0.5,
                            unit_of_measurement=UnitOfTemperature.CELSIUS,
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                    vol.Required(
                        CONF_COMFORT_MAX, default=DEFAULT_COMFORT_MAX
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=10, max=30, step=0.5,
                            unit_of_measurement=UnitOfTemperature.CELSIUS,
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SmartHeatOptionsFlow:
        """Get the options flow."""
        return SmartHeatOptionsFlow(config_entry)


class SmartHeatOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Smart Heat (post-setup tuning)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage comfort settings after setup."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self._config_entry.data
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_COMFORT_MIN,
                        default=current.get(CONF_COMFORT_MIN, DEFAULT_COMFORT_MIN),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=10, max=30, step=0.5,
                            unit_of_measurement=UnitOfTemperature.CELSIUS,
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                    vol.Required(
                        CONF_COMFORT_MAX,
                        default=current.get(CONF_COMFORT_MAX, DEFAULT_COMFORT_MAX),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=10, max=30, step=0.5,
                            unit_of_measurement=UnitOfTemperature.CELSIUS,
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                }
            ),
        )
