# Wiener Netze Smartmeter Integration for Home Assistant

## About

This repo contains a custom component for [Home Assistant](https://www.home-assistant.io) for exposing sensors
providing information about a registered [Wiener Netze Smartmeter](https://www.wienernetze.at/smartmeter).

The main change is the addition of daily values, which are often available earlier than the total consumption. New sensors and statistics have been introduced to assign values to the correct reading date. Additional attributes have been added to the sensors. The authentication flow has been redesigned to reduce the risk of blocking. The YAML configuration has been removed and replaced with a UI-based configuration for the scan interval. Backward compatibility should be maintained, since the main sensors for each metering point remain unchanged.

## Installation

### Manual

Copy `<project-dir>/custom_components/wnsm` into `<home-assistant-root>/config/custom_components`.

## Configuration

Configure the integration via the Home Assistant UI and select your Zählpunkte during setup.

### Sensors, attributes, and statistics overview

Current default setup exposes **3 sensors per Zählpunkt**:

1. Main energy sensor (`METER_READ`, total increasing, legacy-compatible)
2. Total consumption sensor (`METER_READ`, total increasing)
3. Daily consumption sensor (`DAY`, measurement)

Optionally, you can enable up to **2 additional sensors** per Zählpunkt for debugging: the dedicated `DAY` and `METER_READ` reading-date timestamp sensors.

For each active **Zählpunkt**, the integration currently creates the following Home Assistant items:

| Area | Wertetyp source | What gets created | Value shown in HA | Key ID pattern |
|---|---|---|---|---|
| Sensor entity | `METER_READ` | Main energy sensor (legacy-compatible) | Latest METER_READ total value (kWh), total-increasing | `unique_id: <zaehlpunkt>` |
| Sensor entity | `METER_READ` | Total consumption sensor | Latest METER_READ value (kWh), total-increasing snapshot value | `unique_id: <zaehlpunkt>_main_daily_snapshot` |
| Sensor entity | `DAY` | Daily consumption sensor | Latest daily consumption (kWh) | `unique_id: <zaehlpunkt>_day` |
| Sensor entity (optional) | `METER_READ` | METER_READ reading-date timestamp sensor | Effective reading date for the latest METER_READ value | `unique_id: <zaehlpunkt>_meter_read_reading_date` |
| Sensor entity (optional) | `DAY` | DAY reading-date timestamp sensor | Source timestamp for the latest DAY value | `unique_id: <zaehlpunkt>_day_reading_date` |
| Recorder statistics (long-term) | `METER_READ` (main) | Main sensor long-term statistics | Legacy-compatible main stream | `statistic_id: wnsm:<zaehlpunkt-lowercase>` |
| Recorder statistics (long-term) | `METER_READ` (snapshot) | Total consumption long-term statistics | Imported with `start == reading_date` as cumulative total-consumption series (`state = meter_read_kWh`, `sum` derived from deltas) | `statistic_id: wnsm:<slugified-zaehlpunkt>_tot_consump_statistic` |
| Recorder statistics (long-term) | `DAY` | Day statistic long-term statistics | Imported with `start == reading_date` as cumulative day-statistic series (`state = day_kWh`, `sum` cumulative) | `statistic_id: wnsm:<slugified-zaehlpunkt>_day_statistic` |

#### Sensor attributes (current)

- **Main energy sensor** (`<zaehlpunkt>`): includes raw API context and METER_READ helper attributes such as `reading_date`, `reading_dates`, `yesterday`, `day_before_yesterday`, `granularity`, `active`, `smartMeterReady`, and `messwert1` / `messwert2`.
- **Total consumption sensor** (`<zaehlpunkt>_main_daily_snapshot`): same METER_READ-oriented helper attributes as above, especially `reading_date`, `reading_dates`, `messwert1`, `messwert2`.
- **DAY sensor** (`<zaehlpunkt>_day`): includes DAY-oriented helper attributes with `reading_date`, `reading_dates`, and `messwert1` / `messwert2` derived from the latest normalized DAY points.
- **METER_READ reading-date sensor (optional)** (`<zaehlpunkt>_meter_read_reading_date`): exposes timestamp state plus payload attributes (including `reading_date`, `reading_dates`, `messwert1`, `messwert2`) for debugging/validation.
- **DAY reading-date sensor (optional)** (`<zaehlpunkt>_day_reading_date`): exposes the normalized DAY source timestamp as entity state, plus payload attributes for cross-checking the latest DAY datapoints.

#### Important notes

- With **2 Zählpunkte**, you will usually see **6 entities** by default (3 per Zählpunkt, without reading-date sensors). If only one reading-date option is enabled, add **2 entities**. If both reading-date options are enabled, you see **10 entities**.

### Options

- **Scan interval (minutes):** polling interval for sensor updates.
- **Enable DAY reading-date timestamp sensor entity (for debugging only):** disabled by default.
  When enabled, the integration creates an extra DAY timestamp sensor per Zählpunkt (`<zaehlpunkt>_day_reading_date`).
- **Enable METER_READ reading-date timestamp sensor entity (for debugging only):** disabled by default.
  When enabled, the integration creates an extra METER_READ timestamp sensor per Zählpunkt (`<zaehlpunkt>_meter_read_reading_date`).

### Energy Dashboard recommendation

For the **Energy Dashboard (grid consumption, return to grid)**, prefer `wnsm:<slugified-zaehlpunkt>_tot_consump_statistic` as the consumption/return to grid statistic source.

### Recommended Statistics Graph card settings to get the correct Date

Use one series per card (do not mix DAY and snapshot in the same statistics-graph card).

- **Day Statistic example (`_day_statistic`)**

```yaml
chart_type: bar
period: day
type: statistics-graph
entities:
  - wnsm:<slugified-zaehlpunkt>_day_statistic
title: Bezug Wiener Netze Tag
grid_options:
  columns: full
  rows: 6
stat_types:
  - state
```

- **Total Consumption example (`_tot_consump_statistic`)**

```yaml
chart_type: bar
period: day
type: statistics-graph
entities:
  - wnsm:<slugified-zaehlpunkt>_tot_consump_statistic
title: Total Consumption
hide_legend: false
stat_types:
  - state
```

## Copyright

This integration uses the API of https://www.wienernetze.at/smartmeter.
All rights regarding the API are reserved by Wiener Netze.

Special thanks to DarwinsBuddy for providing me a starting point.
Project repository DarwinsBuddy: https://github.com/DarwinsBuddy/WienerNetzeSmartmeter
