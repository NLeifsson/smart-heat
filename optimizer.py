"""Supervisory optimizer for Smart Heat.

Makes recommendations about heat pump setpoints based on:
- Current indoor/outdoor temps
- Heat-loss score (insulation quality)
- Heating effectiveness
- Comfort range
- Time of day (night setback)

Operates in three modes:
- OFF: no recommendations
- SHADOW: logs recommendations but does not act
- AUTO: applies recommendations to climate entities
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from typing import Any

from .const import (
    DEADBAND_C,
    DEFAULT_COMFORT_MAX,
    DEFAULT_COMFORT_MIN,
    EMERGENCY_MIN_TEMP,
    MIN_OFF_TIME_SECONDS,
    MIN_ON_TIME_SECONDS,
    MODE_AUTO,
    MODE_OFF,
    MODE_SHADOW,
)

_LOGGER = logging.getLogger(__name__)


# ── Night schedule ──────────────────────────────────────────────────
NIGHT_START = time(22, 0)
NIGHT_END = time(6, 0)
NIGHT_SETBACK_C = 2.0  # reduce target by 2°C at night
PRE_HEAT_MINUTES = 45  # start pre-heating before night ends


class Action(str, Enum):
    """Optimizer actions."""
    HOLD = "hold"
    HEAT_UP = "heat_up"
    SETBACK = "setback"
    EMERGENCY = "emergency"
    PRE_HEAT = "pre_heat"
    TURN_OFF = "turn_off"


@dataclass
class ZoneState:
    """Input state for one zone."""
    zone_name: str
    indoor_temp: float | None
    outdoor_temp: float | None
    target_temp: float | None
    climate_state: str | None
    heat_loss_score: float | None
    energy_kwh: float | None
    last_action_time: datetime | None  # when the last setpoint change happened
    last_action: Action | None


@dataclass
class OptimizerDecision:
    """Output decision for one zone."""
    zone_name: str
    action: Action
    recommended_target: float | None
    reason: str
    confidence: float  # 0–1


def _is_night(now: datetime) -> bool:
    """Check if current time is in the night setback window."""
    t = now.time()
    if NIGHT_START <= NIGHT_END:
        return NIGHT_START <= t < NIGHT_END
    return t >= NIGHT_START or t < NIGHT_END


def _is_pre_heat_window(now: datetime) -> bool:
    """Check if we're in the pre-heat window before morning."""
    t = now.time()
    pre_heat_start = time(
        NIGHT_END.hour, NIGHT_END.minute - PRE_HEAT_MINUTES
        if NIGHT_END.minute >= PRE_HEAT_MINUTES
        else 60 + NIGHT_END.minute - PRE_HEAT_MINUTES
    )
    # Handle hour rollover
    if NIGHT_END.minute < PRE_HEAT_MINUTES:
        pre_heat_start = time(NIGHT_END.hour - 1, 60 + NIGHT_END.minute - PRE_HEAT_MINUTES)
    else:
        pre_heat_start = time(NIGHT_END.hour, NIGHT_END.minute - PRE_HEAT_MINUTES)
    return pre_heat_start <= t < NIGHT_END


def _min_time_respected(
    last_action_time: datetime | None,
    last_action: Action | None,
    now: datetime,
) -> bool:
    """Check if minimum on/off time has elapsed since last change."""
    if last_action_time is None:
        return True
    elapsed = (now - last_action_time).total_seconds()
    if last_action in (Action.HEAT_UP, Action.PRE_HEAT, Action.EMERGENCY):
        return elapsed >= MIN_ON_TIME_SECONDS
    return elapsed >= MIN_OFF_TIME_SECONDS


def optimize_zone(
    zone: ZoneState,
    comfort_min: float = DEFAULT_COMFORT_MIN,
    comfort_max: float = DEFAULT_COMFORT_MAX,
    now: datetime | None = None,
) -> OptimizerDecision:
    """Generate a control decision for a single zone.

    Returns a decision with action and recommended target temperature.
    Does NOT apply the change — that's the controller's job.
    """
    now = now or datetime.now()

    # ── Missing data → hold ─────────────────────────────────────────
    if zone.indoor_temp is None:
        return OptimizerDecision(
            zone_name=zone.zone_name,
            action=Action.HOLD,
            recommended_target=zone.target_temp,
            reason="Indoor temp unavailable — holding current state",
            confidence=0.0,
        )

    if zone.outdoor_temp is None:
        return OptimizerDecision(
            zone_name=zone.zone_name,
            action=Action.HOLD,
            recommended_target=zone.target_temp,
            reason="Outdoor temp unavailable — holding current state",
            confidence=0.0,
        )

    # ── Emergency: below absolute minimum ───────────────────────────
    if zone.indoor_temp < EMERGENCY_MIN_TEMP:
        return OptimizerDecision(
            zone_name=zone.zone_name,
            action=Action.EMERGENCY,
            recommended_target=comfort_min,
            reason=f"EMERGENCY: {zone.indoor_temp}°C < {EMERGENCY_MIN_TEMP}°C floor",
            confidence=1.0,
        )

    # ── Determine effective target ──────────────────────────────────
    effective_target = (comfort_min + comfort_max) / 2.0

    if _is_pre_heat_window(now):
        # Pre-heat to daytime comfort
        effective_target = comfort_min
        action_hint = Action.PRE_HEAT
        reason_prefix = "Pre-heat window"
    elif _is_night(now):
        effective_target = max(comfort_min - NIGHT_SETBACK_C, EMERGENCY_MIN_TEMP)
        action_hint = Action.SETBACK
        reason_prefix = "Night setback"
    else:
        action_hint = Action.HEAT_UP
        reason_prefix = "Daytime comfort"

    # ── Adjust for insulation quality ───────────────────────────────
    # Poor insulation (high heat-loss score) → bump target slightly to
    # compensate for faster cooling. This is a mild adjustment.
    if zone.heat_loss_score is not None and zone.heat_loss_score > 0:
        # Normalize: typical residential ~50-200 W/°C, poor > 300
        insulation_bump = min(1.0, max(0.0, (zone.heat_loss_score - 150) / 300))
        effective_target += insulation_bump * 0.5  # up to +0.5°C for poor insulation

    # ── Deadband logic ──────────────────────────────────────────────
    diff = zone.indoor_temp - effective_target

    if diff < -DEADBAND_C:
        # Too cold → heat
        if not _min_time_respected(zone.last_action_time, zone.last_action, now):
            return OptimizerDecision(
                zone_name=zone.zone_name,
                action=Action.HOLD,
                recommended_target=zone.target_temp,
                reason="Min time not elapsed — holding",
                confidence=0.5,
            )
        return OptimizerDecision(
            zone_name=zone.zone_name,
            action=action_hint,
            recommended_target=round(effective_target, 1),
            reason=f"{reason_prefix}: {zone.indoor_temp}°C < target {effective_target:.1f}°C",
            confidence=0.8,
        )

    if diff > DEADBAND_C:
        # Too warm → reduce or turn off
        if not _min_time_respected(zone.last_action_time, zone.last_action, now):
            return OptimizerDecision(
                zone_name=zone.zone_name,
                action=Action.HOLD,
                recommended_target=zone.target_temp,
                reason="Min time not elapsed — holding",
                confidence=0.5,
            )
        return OptimizerDecision(
            zone_name=zone.zone_name,
            action=Action.SETBACK,
            recommended_target=round(effective_target, 1),
            reason=f"{zone.indoor_temp}°C > target {effective_target:.1f}°C — reducing",
            confidence=0.8,
        )

    # Within deadband → hold
    return OptimizerDecision(
        zone_name=zone.zone_name,
        action=Action.HOLD,
        recommended_target=zone.target_temp,
        reason=f"Within deadband ({effective_target - DEADBAND_C:.1f}–{effective_target + DEADBAND_C:.1f}°C)",
        confidence=0.9,
    )


def optimize_all_zones(
    zones: list[ZoneState],
    comfort_min: float = DEFAULT_COMFORT_MIN,
    comfort_max: float = DEFAULT_COMFORT_MAX,
    now: datetime | None = None,
) -> list[OptimizerDecision]:
    """Run the optimizer for all zones and return decisions."""
    now = now or datetime.now()
    return [optimize_zone(z, comfort_min, comfort_max, now) for z in zones]
