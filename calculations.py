"""Heat-loss score and heating effectiveness calculations.

These are *relative* metrics — not physical U-values or COP.
They trend over time and help the optimizer make decisions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence

from .const import MIN_DELTA_T_FOR_CALC, ROLLING_WINDOW_HOURS


@dataclass
class AnalyticsSample:
    """A single point-in-time measurement for a zone."""

    timestamp: datetime
    indoor_temp: float  # °C
    outdoor_temp: float  # °C
    energy_kwh: float  # cumulative kWh reading
    climate_state: str  # "heat", "idle", "off", etc.
    floor_area: float = 0.0  # m², 0 = unknown


@dataclass
class HeatLossResult:
    """Result of a heat-loss score calculation."""

    score: float  # W/°C (or W/(m²·°C) if area known) — lower = better insulated
    confidence: float  # 0–1, how much data was usable
    samples_used: int
    samples_total: int
    period_hours: float


@dataclass
class EffectivenessResult:
    """Heating effectiveness: kWh per degree-hour maintained."""

    score: float  # kWh / (°C·h) — lower = more efficient
    total_energy_kwh: float
    total_degree_hours: float
    confidence: float
    samples_used: int


def compute_heat_loss_score(
    samples: Sequence[AnalyticsSample],
    window_hours: float = ROLLING_WINDOW_HOURS,
) -> HeatLossResult | None:
    """Compute relative heat-loss score from a window of samples.

    Uses only quasi-steady-state periods:
    - Climate must be in "heat" mode
    - ΔT must be ≥ MIN_DELTA_T_FOR_CALC
    - Indoor temp must be relatively stable (≤1°C change over the sample)

    Score = average( power_estimate / ΔT ) across valid periods.
    If floor area is known, normalizes to W/(m²·°C).
    """
    if len(samples) < 2:
        return None

    valid_pairs: list[tuple[float, float]] = []  # (power_W, delta_T)
    total = 0

    for i in range(1, len(samples)):
        prev, curr = samples[i - 1], samples[i]
        total += 1

        # Time delta in hours
        dt_hours = (curr.timestamp - prev.timestamp).total_seconds() / 3600.0
        if dt_hours <= 0 or dt_hours > 2.0:
            continue  # skip gaps

        delta_t = curr.indoor_temp - curr.outdoor_temp
        if abs(delta_t) < MIN_DELTA_T_FOR_CALC:
            continue  # not enough temp difference

        # Only use periods where climate is actively heating
        if curr.climate_state not in ("heat", "heating"):
            continue

        # Stability check: indoor temp shouldn't swing more than 1°C
        if abs(curr.indoor_temp - prev.indoor_temp) > 1.0:
            continue

        # Energy consumed in this interval
        energy_delta_kwh = curr.energy_kwh - prev.energy_kwh
        if energy_delta_kwh < 0:
            continue  # meter reset

        # Average power in watts
        power_w = (energy_delta_kwh * 1000.0) / dt_hours if dt_hours > 0 else 0.0
        if power_w <= 0:
            continue

        valid_pairs.append((power_w, delta_t))

    if not valid_pairs:
        return HeatLossResult(
            score=0.0, confidence=0.0, samples_used=0,
            samples_total=total, period_hours=window_hours,
        )

    # Heat-loss score = mean( P / ΔT )
    ratios = [p / dt for p, dt in valid_pairs]
    raw_score = sum(ratios) / len(ratios)

    # Normalize by area if available
    area = samples[0].floor_area
    score = raw_score / area if area > 0 else raw_score

    confidence = min(1.0, len(valid_pairs) / max(1, total * 0.5))

    return HeatLossResult(
        score=round(score, 2),
        confidence=round(confidence, 2),
        samples_used=len(valid_pairs),
        samples_total=total,
        period_hours=window_hours,
    )


def compute_heating_effectiveness(
    samples: Sequence[AnalyticsSample],
) -> EffectivenessResult | None:
    """Compute heating effectiveness: kWh per degree-hour maintained.

    degree-hours = Σ( (T_indoor - T_outdoor) × hours ) across heating periods.
    effectiveness = total_energy / total_degree_hours.
    Lower = more efficient heating system for the building.
    """
    if len(samples) < 2:
        return None

    total_energy = 0.0
    total_degree_hours = 0.0
    valid = 0
    total = 0

    for i in range(1, len(samples)):
        prev, curr = samples[i - 1], samples[i]
        total += 1

        dt_hours = (curr.timestamp - prev.timestamp).total_seconds() / 3600.0
        if dt_hours <= 0 or dt_hours > 2.0:
            continue

        delta_t = curr.indoor_temp - curr.outdoor_temp
        if delta_t <= 0:
            continue  # no meaningful heating load

        energy_delta = curr.energy_kwh - prev.energy_kwh
        if energy_delta < 0:
            continue

        degree_hours = delta_t * dt_hours
        total_energy += energy_delta
        total_degree_hours += degree_hours
        valid += 1

    if valid == 0 or total_degree_hours == 0:
        return None

    score = total_energy / total_degree_hours
    confidence = min(1.0, valid / max(1, total * 0.5))

    return EffectivenessResult(
        score=round(score, 4),
        total_energy_kwh=round(total_energy, 3),
        total_degree_hours=round(total_degree_hours, 2),
        confidence=round(confidence, 2),
        samples_used=valid,
    )
