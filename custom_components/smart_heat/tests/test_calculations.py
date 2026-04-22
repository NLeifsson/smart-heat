"""Tests for Smart Heat calculations module."""

from datetime import datetime, timedelta

import pytest

from custom_components.smart_heat.calculations import (
    AnalyticsSample,
    compute_heat_loss_score,
    compute_heating_effectiveness,
)


def _make_samples(
    count: int = 24,
    indoor: float = 21.0,
    outdoor: float = 0.0,
    base_energy: float = 100.0,
    energy_per_step: float = 2.0,
    climate_state: str = "heat",
    interval_minutes: int = 60,
    floor_area: float = 0.0,
) -> list[AnalyticsSample]:
    """Generate a sequence of stable samples."""
    base = datetime(2025, 1, 15, 0, 0, 0)
    return [
        AnalyticsSample(
            timestamp=base + timedelta(minutes=i * interval_minutes),
            indoor_temp=indoor,
            outdoor_temp=outdoor,
            energy_kwh=base_energy + i * energy_per_step,
            climate_state=climate_state,
            floor_area=floor_area,
        )
        for i in range(count)
    ]


# ── Heat Loss Score ─────────────────────────────────────────────────


class TestHeatLossScore:
    def test_basic_calculation(self):
        """Stable heating at 21°C indoor, 0°C outdoor, 2 kWh/h → should produce a score."""
        samples = _make_samples()
        result = compute_heat_loss_score(samples)
        assert result is not None
        assert result.score > 0
        assert result.samples_used > 0
        assert result.confidence > 0

    def test_score_higher_for_more_energy(self):
        """More energy at same ΔT → higher heat-loss score (worse insulation)."""
        good = _make_samples(energy_per_step=1.0)
        bad = _make_samples(energy_per_step=4.0)
        good_result = compute_heat_loss_score(good)
        bad_result = compute_heat_loss_score(bad)
        assert good_result is not None and bad_result is not None
        assert bad_result.score > good_result.score

    def test_normalizes_by_area(self):
        """With floor area, score should be lower (per m²)."""
        no_area = _make_samples(floor_area=0.0)
        with_area = _make_samples(floor_area=100.0)
        r1 = compute_heat_loss_score(no_area)
        r2 = compute_heat_loss_score(with_area)
        assert r1 is not None and r2 is not None
        assert r2.score < r1.score

    def test_skips_non_heating(self):
        """Only 'heat' state samples should be used."""
        samples = _make_samples(climate_state="off")
        result = compute_heat_loss_score(samples)
        assert result is not None
        assert result.samples_used == 0

    def test_skips_small_delta_t(self):
        """ΔT < 3°C should be excluded."""
        samples = _make_samples(indoor=20.0, outdoor=19.0)
        result = compute_heat_loss_score(samples)
        assert result is not None
        assert result.samples_used == 0

    def test_too_few_samples(self):
        """Fewer than 2 samples → None."""
        result = compute_heat_loss_score([_make_samples(count=1)[0]])
        assert result is None

    def test_handles_energy_reset(self):
        """Energy going backward (meter reset) should be skipped."""
        samples = _make_samples(count=5)
        # Simulate reset at sample 3
        samples[3] = AnalyticsSample(
            timestamp=samples[3].timestamp,
            indoor_temp=21.0,
            outdoor_temp=0.0,
            energy_kwh=0.0,  # reset
            climate_state="heat",
        )
        result = compute_heat_loss_score(samples)
        assert result is not None
        # Should still work with remaining valid pairs


# ── Heating Effectiveness ───────────────────────────────────────────


class TestHeatingEffectiveness:
    def test_basic_calculation(self):
        """Standard heating should produce an effectiveness score."""
        samples = _make_samples()
        result = compute_heating_effectiveness(samples)
        assert result is not None
        assert result.score > 0
        assert result.total_energy_kwh > 0
        assert result.total_degree_hours > 0

    def test_more_efficient_lower_score(self):
        """Less energy for same conditions → lower score (more efficient)."""
        efficient = _make_samples(energy_per_step=1.0)
        wasteful = _make_samples(energy_per_step=4.0)
        r1 = compute_heating_effectiveness(efficient)
        r2 = compute_heating_effectiveness(wasteful)
        assert r1 is not None and r2 is not None
        assert r1.score < r2.score

    def test_no_heating_load(self):
        """Indoor ≤ outdoor → no degree-hours → None."""
        samples = _make_samples(indoor=5.0, outdoor=10.0)
        result = compute_heating_effectiveness(samples)
        assert result is None

    def test_too_few_samples(self):
        result = compute_heating_effectiveness([_make_samples(count=1)[0]])
        assert result is None
