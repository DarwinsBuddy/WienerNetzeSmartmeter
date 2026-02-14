"""WienerNetze Smartmeter sensor platform."""

from datetime import timedelta

from homeassistant import config_entries, core
from homeassistant.const import CONF_SCAN_INTERVAL

from .const import (
    CONF_ENABLE_DAY_STATISTICS_IMPORT,
    CONF_ZAEHLPUNKTE,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from .day_sensor import WNSMDailySensor
from .day_reading_date_sensor import WNSMDayReadingDateSensor
from .meter_read_reading_date_sensor import WNSMMeterReadReadingDateSensor
from .main_daily_snapshot_sensor import WNSMMainDailySnapshotSensor
from .wnsm_sensor import WNSMSensor


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    """Setup sensors from a config entry created in the integrations UI."""
    runtime_data = config_entry.runtime_data
    if runtime_data is not None and hasattr(runtime_data, "config"):
        config = runtime_data.config
        async_smartmeter = runtime_data.async_smartmeter
    else:
        # Backward compatibility fallback.
        config = hass.data[DOMAIN][config_entry.entry_id]
        async_smartmeter = None

    scan_interval_minutes = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
    scan_interval = timedelta(minutes=scan_interval_minutes)

    wnsm_sensors = [
        WNSMSensor(
            async_smartmeter,
            config["username"],
            config["password"],
            zp["zaehlpunktnummer"],
            scan_interval,
        )
        for zp in config[CONF_ZAEHLPUNKTE]
    ]
    wnsm_sensors.extend(
        [
            WNSMMainDailySnapshotSensor(
                async_smartmeter,
                config["username"],
                config["password"],
                zp["zaehlpunktnummer"],
                scan_interval,
            )
            for zp in config[CONF_ZAEHLPUNKTE]
        ]
    )
    wnsm_sensors.extend(
        [
            WNSMDailySensor(
                async_smartmeter,
                config["username"],
                config["password"],
                zp["zaehlpunktnummer"],
                config.get(CONF_ENABLE_DAY_STATISTICS_IMPORT, True),
                scan_interval,
            )
            for zp in config[CONF_ZAEHLPUNKTE]
        ]
    )
    wnsm_sensors.extend(
        [
            WNSMDayReadingDateSensor(
                async_smartmeter,
                config["username"],
                config["password"],
                zp["zaehlpunktnummer"],
                scan_interval,
            )
            for zp in config[CONF_ZAEHLPUNKTE]
        ]
    )
    wnsm_sensors.extend(
        [
            WNSMMeterReadReadingDateSensor(
                async_smartmeter,
                config["username"],
                config["password"],
                zp["zaehlpunktnummer"],
                scan_interval,
            )
            for zp in config[CONF_ZAEHLPUNKTE]
        ]
    )
    async_add_entities(wnsm_sensors, update_before_add=True)
