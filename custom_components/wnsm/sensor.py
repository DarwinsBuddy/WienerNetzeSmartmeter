"""
WienerNetze Smartmeter sensor platform
"""
import collections
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
from homeassistant.core import DOMAIN
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)
from .const import CONF_ZAEHLPUNKTE
from .statistics_sensor import StatisticsSensor
from .live_sensor import LiveSensor
# Time between updating data from Wiener Netze
SCAN_INTERVAL = timedelta(minutes=60)
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
    """Setup sensors from a config entry created in the integrations UI."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    live_sensors = [
        LiveSensor(config[CONF_USERNAME], config[CONF_PASSWORD], zp["zaehlpunktnummer"])
        for zp in config[CONF_ZAEHLPUNKTE]
    ]
    historical_sensors = [
        StatisticsSensor(config[CONF_USERNAME], config[CONF_PASSWORD], zp["zaehlpunktnummer"])
        for zp in config[CONF_ZAEHLPUNKTE]
    ]
    async_add_entities(historical_sensors, update_before_add=True)
    async_add_entities(live_sensors, update_before_add=True)


async def async_setup_platform(
    hass: HomeAssistantType,  # pylint: disable=unused-argument
    config: ConfigType,
    async_add_entities: collections.abc.Callable,
    discovery_info: Optional[
        DiscoveryInfoType
    ] = None,  # pylint: disable=unused-argument
) -> None:
    """Set up the sensor platform by adding it into configuration.yaml"""
    live_sensor = LiveSensor(config[CONF_USERNAME], config[CONF_PASSWORD], config[CONF_DEVICE_ID])
    historical_sensor = StatisticsSensor(config[CONF_USERNAME], config[CONF_PASSWORD], config[CONF_DEVICE_ID])
    async_add_entities([live_sensor, historical_sensor], update_before_add=True)
