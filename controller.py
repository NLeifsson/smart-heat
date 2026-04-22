"""Event-driven supervisory controller for Smart Heat.

Listens to state changes on climate and sensor entities.
Runs the optimizer and applies decisions when in AUTO mode.
Logs all decisions to the database.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    SERVICE_SET_TEMPERATURE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_CLIMATE_ENTITY,
    CONF_ZONES,
    CONF_ZONE_NAME,
    DOMAIN,
    MODE_AUTO,
    MODE_OFF,
    MODE_SHADOW,
)
from .coordinator import SmartHeatCoordinator, SmartHeatData
from .database import SmartHeatDatabase
from .optimizer import Action, OptimizerDecision, ZoneState, optimize_zone

_LOGGER = logging.getLogger(__name__)


class SmartHeatController:
    """Supervisory controller that bridges optimizer decisions to climate entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: SmartHeatCoordinator,
        database: SmartHeatDatabase,
        entry: ConfigEntry,
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._db = database
        self._entry = entry
        self._unsub_listeners: list[Any] = []
        self._last_actions: dict[str, tuple[datetime, Action]] = {}

    @property
    def control_mode(self) -> str:
        """Get the current control mode from the select entity."""
        entity_id = f"select.{DOMAIN}_control_mode"
        state = self._hass.states.get(entity_id)
        if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return state.state
        return MODE_OFF

    def get_comfort_range(self) -> tuple[float, float]:
        """Read comfort min/max from number entities."""
        min_id = f"number.{DOMAIN}_comfort_minimum"
        max_id = f"number.{DOMAIN}_comfort_maximum"
        comfort_min = 19.0
        comfort_max = 22.0
        min_state = self._hass.states.get(min_id)
        max_state = self._hass.states.get(max_id)
        if min_state and min_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                comfort_min = float(min_state.state)
            except (ValueError, TypeError):
                pass
        if max_state and max_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                comfort_max = float(max_state.state)
            except (ValueError, TypeError):
                pass
        return comfort_min, comfort_max

    async def async_start(self) -> None:
        """Start listening to entity state changes."""
        # Track all climate and sensor entities we care about
        entities_to_track: list[str] = []
        for zone_cfg in self._entry.data[CONF_ZONES]:
            entities_to_track.append(zone_cfg[CONF_CLIMATE_ENTITY])
        # Also track the control mode select
        entities_to_track.append(f"select.{DOMAIN}_control_mode")

        self._unsub_listeners.append(
            async_track_state_change_event(
                self._hass, entities_to_track, self._on_state_change
            )
        )
        _LOGGER.info("SmartHeatController started, tracking %d entities", len(entities_to_track))

    @callback
    def _on_state_change(self, event: Event) -> None:
        """Handle state changes — schedule an optimization run."""
        if self.control_mode == MODE_OFF:
            return
        self._hass.async_create_task(self._run_optimization())

    async def _run_optimization(self) -> None:
        """Run the optimizer for all zones and apply decisions."""
        data: SmartHeatData = self._coordinator.data
        if data is None:
            return

        mode = self.control_mode
        if mode == MODE_OFF:
            return

        comfort_min, comfort_max = self.get_comfort_range()
        now = datetime.now()

        for zone_name, zone_data in data.zones.items():
            last = self._last_actions.get(zone_name)
            zone_state = ZoneState(
                zone_name=zone_name,
                indoor_temp=zone_data.indoor_temp_avg,
                outdoor_temp=data.outdoor_temp,
                target_temp=zone_data.climate_target_temp,
                climate_state=zone_data.climate_state,
                heat_loss_score=None,  # populated by analytics in Phase 2
                energy_kwh=zone_data.energy_kwh,
                last_action_time=last[0] if last else None,
                last_action=last[1] if last else None,
            )

            decision = optimize_zone(zone_state, comfort_min, comfort_max, now)

            # Log every decision
            await self._db.log_decision(
                zone_name=zone_name,
                control_mode=mode,
                action=decision.action.value,
                reason=decision.reason,
                current_temp=zone_data.indoor_temp_avg,
                target_temp=decision.recommended_target,
                outdoor_temp=data.outdoor_temp,
                heat_loss_score=None,
                applied=(mode == MODE_AUTO and decision.action != Action.HOLD),
            )

            # Apply in AUTO mode
            if mode == MODE_AUTO and decision.action != Action.HOLD:
                await self._apply_decision(zone_data.climate_entity, decision, now, zone_name)
            elif mode == MODE_SHADOW and decision.action != Action.HOLD:
                _LOGGER.info(
                    "[SHADOW] Zone %s: would %s → target %s°C (%s)",
                    zone_name, decision.action.value,
                    decision.recommended_target, decision.reason,
                )

    async def _apply_decision(
        self,
        climate_entity: str,
        decision: OptimizerDecision,
        now: datetime,
        zone_name: str,
    ) -> None:
        """Apply a decision to a climate entity."""
        if decision.recommended_target is None:
            return

        try:
            await self._hass.services.async_call(
                "climate",
                SERVICE_SET_TEMPERATURE,
                {
                    "entity_id": climate_entity,
                    ATTR_TEMPERATURE: decision.recommended_target,
                },
                blocking=True,
            )
            self._last_actions[zone_name] = (now, decision.action)
            _LOGGER.info(
                "[AUTO] Zone %s: %s → set %s to %s°C (%s)",
                zone_name, decision.action.value,
                climate_entity, decision.recommended_target, decision.reason,
            )
        except Exception:
            _LOGGER.exception(
                "Failed to apply decision to %s", climate_entity
            )

    async def async_stop(self) -> None:
        """Unsubscribe from state listeners."""
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()
        _LOGGER.debug("SmartHeatController stopped")
