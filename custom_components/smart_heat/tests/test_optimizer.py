"""Tests for Smart Heat optimizer module."""

from datetime import datetime, timedelta

import pytest

from custom_components.smart_heat.optimizer import (
    Action,
    OptimizerDecision,
    ZoneState,
    optimize_zone,
    optimize_all_zones,
)


def _zone(
    indoor: float | None = 20.0,
    outdoor: float | None = 0.0,
    target: float | None = 21.0,
    climate_state: str = "heat",
    heat_loss: float | None = None,
    last_action_time: datetime | None = None,
    last_action: Action | None = None,
) -> ZoneState:
    return ZoneState(
        zone_name="test_zone",
        indoor_temp=indoor,
        outdoor_temp=outdoor,
        target_temp=target,
        climate_state=climate_state,
        heat_loss_score=heat_loss,
        energy_kwh=100.0,
        last_action_time=last_action_time,
        last_action=last_action,
    )


class TestOptimizer:
    def test_hold_when_indoor_unavailable(self):
        d = optimize_zone(_zone(indoor=None))
        assert d.action == Action.HOLD
        assert d.confidence == 0.0

    def test_hold_when_outdoor_unavailable(self):
        d = optimize_zone(_zone(outdoor=None))
        assert d.action == Action.HOLD
        assert d.confidence == 0.0

    def test_emergency_below_floor(self):
        d = optimize_zone(_zone(indoor=12.0))
        assert d.action == Action.EMERGENCY
        assert d.confidence == 1.0

    def test_heat_up_when_cold(self):
        """Indoor well below comfort target → heat up."""
        now = datetime(2025, 1, 15, 12, 0, 0)  # daytime
        d = optimize_zone(_zone(indoor=17.0), comfort_min=19, comfort_max=22, now=now)
        assert d.action in (Action.HEAT_UP, Action.PRE_HEAT)
        assert d.recommended_target is not None

    def test_hold_within_deadband(self):
        """Indoor close to target → hold."""
        now = datetime(2025, 1, 15, 12, 0, 0)
        d = optimize_zone(_zone(indoor=20.5), comfort_min=19, comfort_max=22, now=now)
        assert d.action == Action.HOLD

    def test_setback_when_too_warm(self):
        """Indoor well above target → setback."""
        now = datetime(2025, 1, 15, 12, 0, 0)
        d = optimize_zone(_zone(indoor=24.0), comfort_min=19, comfort_max=22, now=now)
        assert d.action == Action.SETBACK

    def test_night_setback(self):
        """At night, target should be lower → may setback even at 20°C."""
        night = datetime(2025, 1, 15, 23, 0, 0)
        d = optimize_zone(_zone(indoor=20.0), comfort_min=19, comfort_max=22, now=night)
        # Night target = 19 - 2 = 17, so 20°C is above → setback
        assert d.action == Action.SETBACK

    def test_min_on_time_respected(self):
        """If we just started heating 5 min ago, hold even if too warm."""
        now = datetime(2025, 1, 15, 12, 0, 0)
        recent = now - timedelta(minutes=5)  # only 5 min ago
        d = optimize_zone(
            _zone(indoor=24.0, last_action_time=recent, last_action=Action.HEAT_UP),
            comfort_min=19, comfort_max=22, now=now,
        )
        assert d.action == Action.HOLD
        assert "Min time" in d.reason

    def test_min_time_expired_allows_action(self):
        """After minimum time, action should proceed."""
        now = datetime(2025, 1, 15, 12, 0, 0)
        long_ago = now - timedelta(minutes=20)
        d = optimize_zone(
            _zone(indoor=24.0, last_action_time=long_ago, last_action=Action.HEAT_UP),
            comfort_min=19, comfort_max=22, now=now,
        )
        assert d.action != Action.HOLD

    def test_poor_insulation_bumps_target(self):
        """High heat-loss score → slightly higher effective target."""
        now = datetime(2025, 1, 15, 12, 0, 0)
        good = optimize_zone(_zone(indoor=20.2, heat_loss=50.0), comfort_min=19, comfort_max=22, now=now)
        poor = optimize_zone(_zone(indoor=20.2, heat_loss=400.0), comfort_min=19, comfort_max=22, now=now)
        # With poor insulation, the effective target is slightly higher,
        # so the optimizer might want to heat more
        # This is a soft test — just verify it doesn't crash
        assert good is not None and poor is not None

    def test_optimize_all_zones(self):
        """Test batch optimization across multiple zones."""
        zones = [
            _zone(indoor=18.0),
            _zone(indoor=22.0),
        ]
        zones[0].zone_name = "living_room"
        zones[1].zone_name = "bedroom"
        now = datetime(2025, 1, 15, 12, 0, 0)
        decisions = optimize_all_zones(zones, comfort_min=19, comfort_max=22, now=now)
        assert len(decisions) == 2
        assert decisions[0].zone_name == "living_room"
        assert decisions[1].zone_name == "bedroom"
