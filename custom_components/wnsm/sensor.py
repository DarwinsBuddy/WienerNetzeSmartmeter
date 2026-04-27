import collections.abc
from datetime import timedelta
from typing import Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import core, config_entries
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA
)
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICE_ID
)
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
)
from .const import CONF_ZAEHLPUNKTE, DOMAIN
from .wnsm_sensor import WNSMSensor, WNSMSensorType

SCAN_INTERVAL = timedelta(minutes=60 * 6)
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_DEVICE_ID): cv.string,
    }
)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    config = hass.data[DOMAIN][config_entry.entry_id]
    wnsm_sensors = [
        sensor
        for zp in config[CONF_ZAEHLPUNKTE]
        for sensor in (
            WNSMSensor(config[CONF_USERNAME], config[CONF_PASSWORD], zp["zaehlpunktnummer"], WNSMSensorType.CONSUMPTION),
            WNSMSensor(config[CONF_USERNAME], config[CONF_PASSWORD], zp["zaehlpunktnummer"], WNSMSensorType.FEED_IN),
            WNSMSensor(config[CONF_USERNAME], config[CONF_PASSWORD], zp["zaehlpunktnummer"], WNSMSensorType.NET_GRID_BALANCE),
        )
    ]
    async_add_entities(wnsm_sensors, update_before_add=True)


async def async_setup_platform(
    hass: core.HomeAssistant,
    config: ConfigType,
    async_add_entities: collections.abc.Callable,
    discovery_info: Optional[
        DiscoveryInfoType
    ] = None,
) -> None:
    wnsm_sensors = [
        WNSMSensor(config[CONF_USERNAME], config[CONF_PASSWORD], config[CONF_DEVICE_ID], WNSMSensorType.CONSUMPTION),
        WNSMSensor(config[CONF_USERNAME], config[CONF_PASSWORD], config[CONF_DEVICE_ID], WNSMSensorType.FEED_IN),
        WNSMSensor(config[CONF_USERNAME], config[CONF_PASSWORD], config[CONF_DEVICE_ID], WNSMSensorType.NET_GRID_BALANCE),
    ]
    async_add_entities(wnsm_sensors, update_before_add=True)
