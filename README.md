# Smart Heat — Home Assistant Custom Integration

Supervisory heating control with analytics for multi-zone heat pump setups.

## Features

- **Multi-zone monitoring** — indoor/outdoor temps, energy usage, ΔT per zone
- **Heat-loss score** — relative insulation quality metric (lower = better)
- **Heating effectiveness** — kWh per degree-hour maintained (lower = more efficient)
- **Supervisory optimizer** — deadband, min on/off times, night setback, pre-heating
- **Three control modes** — Off / Shadow (log-only) / Auto
- **SQLite decision log** — tracks all optimizer decisions for review
- **Example dashboard** — ready-to-use Lovelace YAML included

## Requirements

- Home Assistant 2024.1.0+
- Heat pumps exposed as `climate` entities
- Indoor temperature sensors per zone
- Outdoor temperature sensor
- Energy sensors (kWh) per heat pump

## Installation (HACS)

1. Open HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/NLeifsson/smart-heat` as **Integration**
3. Search for "Smart Heat" and install
4. Restart Home Assistant
5. Go to Settings → Integrations → Add → **Smart Heat**

## Configuration

The config flow guides you through:
1. Select outdoor temperature sensor
2. Add zones (heat pump + indoor sensors + energy sensor per zone)
3. Set comfort temperature range

## Control Modes

| Mode | Behavior |
|------|----------|
| **Off** | Read-only monitoring, no control |
| **Shadow** | Logs recommendations but doesn't act |
| **Auto** | Applies optimizer decisions to heat pumps |

> **Recommended:** Start in Shadow mode to verify decisions before enabling Auto.

## Safety Features

- ±0.5°C deadband (hysteresis)
- 10 min minimum on-time, 5 min minimum off-time
- 15°C emergency temperature floor
- Stale sensor detection (30 min timeout)
- All decisions logged to SQLite

## Dashboard

Copy `example_dashboard.yaml` into your Lovelace config (raw editor).
Adjust entity IDs to match your zone names.

## License

MIT
