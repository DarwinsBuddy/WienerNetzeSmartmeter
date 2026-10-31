"""
WienerNetze Smartmeter sensor platform
"""
import collections.abc
from datetime import timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Optional

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
from .const import CONF_FEED_IN_PRICE_PER_KWH, CONF_PRICE_PER_KWH, CONF_ZAEHLPUNKTE, DOMAIN
from .wnsm_sensor import WNSMSensor
# Time between updating data from Wiener Netze
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
    """Setup sensors from a config entry created in the integrations UI."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    price_per_kwh = _price(config_entry.options, CONF_PRICE_PER_KWH)
    feed_in_price_per_kwh = _price(config_entry.options, CONF_FEED_IN_PRICE_PER_KWH)
    wnsm_sensors = [
        WNSMSensor(config[CONF_USERNAME], config[CONF_PASSWORD], zp["zaehlpunktnummer"],
                   price_per_kwh=price_per_kwh, feed_in_price_per_kwh=feed_in_price_per_kwh)
        for zp in config[CONF_ZAEHLPUNKTE]
    ]
    async_add_entities(wnsm_sensors, update_before_add=True)


def _price(options: MappingProxyType[str, Any], key: str) -> Optional[Decimal]:
    value = options.get(key)
    return Decimal(str(value)) if value is not None else None


async def async_setup_platform(
    hass: core.HomeAssistant,  # pylint: disable=unused-argument
    config: ConfigType,
    async_add_entities: collections.abc.Callable,
    discovery_info: Optional[
        DiscoveryInfoType
    ] = None,  # pylint: disable=unused-argument
) -> None:
    """Set up the sensor platform by adding it into configuration.yaml"""
    wnsm_sensor = WNSMSensor(config[CONF_USERNAME], config[CONF_PASSWORD], config[CONF_DEVICE_ID])
    async_add_entities([wnsm_sensor], update_before_add=True)
