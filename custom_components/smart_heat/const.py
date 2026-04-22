"""Constants for Smart Heat integration."""

DOMAIN = "smart_heat"
PLATFORMS = ["sensor", "select", "number"]

# ── Configuration keys ──────────────────────────────────────────────
CONF_ZONES = "zones"
CONF_ZONE_NAME = "zone_name"
CONF_CLIMATE_ENTITY = "climate_entity"
CONF_INDOOR_TEMP_SENSORS = "indoor_temp_sensors"
CONF_OUTDOOR_TEMP_SENSOR = "outdoor_temp_sensor"
CONF_ENERGY_SENSOR = "energy_sensor"
CONF_FLOOR_AREA = "floor_area"  # m², optional
CONF_COMFORT_MIN = "comfort_min"
CONF_COMFORT_MAX = "comfort_max"

# ── Defaults ────────────────────────────────────────────────────────
DEFAULT_COMFORT_MIN = 19.0  # °C
DEFAULT_COMFORT_MAX = 22.0  # °C
DEFAULT_SCAN_INTERVAL = 900  # 15 minutes for analytics
DEFAULT_FLOOR_AREA = 0.0  # 0 = unknown

# ── Control modes ───────────────────────────────────────────────────
MODE_OFF = "off"
MODE_SHADOW = "shadow"
MODE_AUTO = "auto"
CONTROL_MODES = [MODE_OFF, MODE_SHADOW, MODE_AUTO]

# ── Optimizer safety limits ─────────────────────────────────────────
MIN_ON_TIME_SECONDS = 600  # 10 min minimum run
MIN_OFF_TIME_SECONDS = 300  # 5 min minimum off
DEADBAND_C = 0.5  # ±0.5°C hysteresis
STALE_SENSOR_SECONDS = 1800  # 30 min = stale
EMERGENCY_MIN_TEMP = 15.0  # °C absolute floor

# ── Analytics ───────────────────────────────────────────────────────
ROLLING_WINDOW_HOURS = 24
MIN_DELTA_T_FOR_CALC = 3.0  # need ≥3°C indoor-outdoor diff for meaningful calc
