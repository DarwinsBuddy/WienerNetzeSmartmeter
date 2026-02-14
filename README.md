# Wiener Netze Smartmeter Integration for Home Assistant

## About 

This repo contains a custom component for [Home Assistant](https://www.home-assistant.io) for exposing a sensor
providing information about a registered [WienerNetze Smartmeter](https://www.wienernetze.at/smartmeter).

## Sensors

Current default setup (with temporary cleanup enabled) exposes **3 sensors per Zählpunkt**:

1. Main daily snapshot sensor (`METER_READ`, total increasing)
2. Daily consumption sensor (`DAY`, measurement)
3. METER_READ reading-date timestamp sensor

Configuration options in the UI include scan interval (minutes) and optional DAY statistics import.

### Entity and statistics overview by Zählpunkt and Wertetyp

For each active **Zählpunkt**, the integration currently creates the following Home Assistant items:

| Area | Wertetyp source | What gets created | Value shown in HA | Unique/statistic ID pattern |
|---|---|---|---|---|
| Sensor entity | `METER_READ` | Main daily snapshot sensor | Latest METER_READ value (kWh), total-increasing snapshot value | `unique_id: <zaehlpunkt>_main_daily_snapshot` |
| Sensor entity | `DAY` | Daily consumption sensor | Latest daily consumption (kWh) | `unique_id: <zaehlpunkt>_day` |
| Sensor entity | `METER_READ` | METER_READ reading-date timestamp sensor | Effective reading date for the latest METER_READ value | `unique_id: <zaehlpunkt>_meter_read_reading_date` |
| Recorder statistics (long-term) | `METER_READ` (snapshot) | Main daily snapshot long-term statistics series | Imported with `start == reading_date` as cumulative snapshot series (`state = meter_read_kWh`, `sum` derived from deltas) | `statistic_id: wnsm:<slugified-zaehlpunkt>_main_daily_snapshot_v3` |
| Recorder statistics (long-term, optional) | `DAY` | Additional DAY long-term statistics series (enabled via option) | One statistic point per day (`state = day kWh`, `sum = None`) | `statistic_id: wnsm:<slugified-zaehlpunkt>_day_v2` |

#### Important notes

- Enabling **DAY statistics import** does **not** create extra entities. It adds an extra recorder/long-term statistics series for DAY values.
- DAY and snapshot long-term statistics use versioned IDs (`_day_v2`, `_main_daily_snapshot_v3`) so new installs/upgrades get clean metadata without reusing stale recorder entries.
- With **2 Zählpunkte**, you will usually see **6 entities** (3 per Zählpunkt). If DAY stats import is enabled, you also get **2 extra long-term statistics series** (one per Zählpunkt).
- Legacy entities (`<zaehlpunkt>` main sensor and `<zaehlpunkt>_day_reading_date`) are currently commented out in setup for cleanup and can be re-enabled later.

## Installation

### Manual

Copy `<project-dir>/custom_components/wnsm` into `<home-assistant-root>/config/custom_components`

## Configuration

Configure the integration via the Home Assistant UI and select your Zählpunkte during setup.
<img width="679" height="733" alt="grafik" src="https://github.com/user-attachments/assets/bc0a75b4-23d8-41fb-9205-3db182f2ae77" />


### Authentication flow (redesigned to reduce blocking risk)

To reduce the risk of Wiener Netze login/session blocking, the integration uses a redesigned auth flow:

- A shared Smartmeter client instance is reused per config entry to avoid unnecessary repeated full logins.
- Login calls are serialized with a lock, so parallel sensor updates do not trigger concurrent login storms.
- API calls use automatic re-authentication/retry on connection/session failures (for example expired/unauthorized responses).

This keeps request patterns more stable while preserving the same sensor/statistics behavior.

### Setup behavior (current implementation)

- The integration currently creates **3 entities per active Zählpunkt**:
  1. Main daily snapshot sensor (`METER_READ`, total increasing)
  2. Daily consumption sensor (`DAY`, measurement)
  3. METER_READ reading-date timestamp sensor
- With 2 Zählpunkte, this results in **6 entities**.
- Legacy main and DAY-reading-date entities are intentionally disabled in setup and can be brought back quickly.

### Options

- **Scan interval (minutes):** polling interval for sensor updates.
- **Enable DAY statistics import to long-term recorder:** enabled by default.  
  When enabled, the integration imports an additional DAY long-term statistics series (`wnsm:<slugified-zaehlpunkt>_day_v2`).

### Long-term statistics and Energy Dashboard

- Legacy main sensor long-term statistics (`wnsm:<zaehlpunkt-lowercase>`) exist only when the legacy main entity is re-enabled.
- DAY long-term statistics are optional and imported as daily points (`state=day kWh`, `sum=None`).
- Main daily snapshot long-term statistics are imported as cumulative totals (`has_sum=True`) while preserving source `reading_date` timestamps.
- For the **Energy Dashboard (grid consumption)**, prefer `wnsm:<slugified-zaehlpunkt>_main_daily_snapshot_v3` as the consumption statistic source.

### Recommended Statistics Graph card settings

Use one series per card (do not mix DAY and snapshot in the same statistics-graph card).

- **Daily values (DAY):**
  - Statistic: `wnsm:<slugified-zaehlpunkt>_day_v2`
  - Period: `day`
  - Stat type: `max`
  - Chart type: `bar`

- **Total consumption trend (snapshot cumulative):**
  - Statistic: `wnsm:<slugified-zaehlpunkt>_main_daily_snapshot_v3`
  - Period: `day`
  - Stat type: `change`
  - Chart type: `bar` (or `line`)

These settings match the current statistics semantics and avoid empty charts caused by mixing incompatible statistic types in a single card.

## Copyright

This integration uses the API of https://www.wienernetze.at/smartmeter.
All rights regarding the API are reserved by Wiener Netze.

Special thanks to DarwinsBuddy for providing me a starting point.
Project repository DarwinsBuddy: https://github.com/DarwinsBuddy/WienerNetzeSmartmeter
