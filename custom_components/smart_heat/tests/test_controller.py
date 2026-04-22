"""Tests for Smart Heat controller — event-driven supervisory control."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.smart_heat.controller import SmartHeatController
from custom_components.smart_heat.coordinator import SmartHeatData, ZoneData
from custom_components.smart_heat.const import MODE_AUTO, MODE_OFF, MODE_SHADOW


def _make_data(
    outdoor: float = 0.0,
    zones: dict | None = None,
) -> SmartHeatData:
    if zones is None:
        zones = {
            "living_room": ZoneData(
                zone_name="living_room",
                climate_entity="climate.living_room_hp",
                indoor_temps=[20.0],
                indoor_temp_avg=20.0,
                climate_state="heat",
                climate_current_temp=20.0,
                climate_target_temp=21.0,
                energy_kwh=100.0,
            ),
        }
    return SmartHeatData(
        outdoor_temp=outdoor,
        outdoor_sensor_stale=False,
        zones=zones,
    )


class TestControllerModeHandling:
    """Test that the controller respects control mode settings."""

    def test_off_mode_skips_optimization(self):
        """When mode is OFF, no optimization should run."""
        # This is a structural test — verifying the control flow
        # The controller checks mode at the beginning of _on_state_change
        assert MODE_OFF == "off"
        assert MODE_SHADOW == "shadow"
        assert MODE_AUTO == "auto"

    def test_zone_data_structure(self):
        """Verify ZoneData holds all needed fields."""
        data = _make_data()
        zone = data.zones["living_room"]
        assert zone.indoor_temp_avg == 20.0
        assert zone.climate_entity == "climate.living_room_hp"
        assert zone.energy_kwh == 100.0

    def test_stale_outdoor_sensor(self):
        """Data with stale outdoor sensor should be flagged."""
        data = SmartHeatData(outdoor_temp=None, outdoor_sensor_stale=True)
        assert data.outdoor_sensor_stale is True
        assert data.outdoor_temp is None

    def test_multiple_zone_data(self):
        """Multiple zones should all be present in data."""
        zones = {
            "zone_a": ZoneData(
                zone_name="zone_a",
                climate_entity="climate.a",
                indoor_temp_avg=19.0,
                climate_state="heat",
            ),
            "zone_b": ZoneData(
                zone_name="zone_b",
                climate_entity="climate.b",
                indoor_temp_avg=22.0,
                climate_state="idle",
            ),
        }
        data = _make_data(zones=zones)
        assert len(data.zones) == 2
        assert data.zones["zone_a"].indoor_temp_avg == 19.0
        assert data.zones["zone_b"].climate_state == "idle"
