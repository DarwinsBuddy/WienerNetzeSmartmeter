"""
WienerNetze Smartmeter sensor platform
"""
import collections
import logging
from datetime import timedelta, datetime
from typing import Any, Optional

import voluptuous as vol
from homeassistant import core, config_entries

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICE_ID,
    ENERGY_KILO_WATT_HOUR,
)
from homeassistant.core import DOMAIN
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)

from .api import Smartmeter
from .const import (
    ATTRS_WELCOME_CALL,
    ATTRS_ZAEHLPUNKTE_CALL,
    CONF_ZAEHLPUNKTE,
)
from .utils import before, today, translate_dict

_LOGGER = logging.getLogger(__name__)
# Time between updating data from Wiener Netze
SCAN_INTERVAL = timedelta(minutes=15)

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
    sensors = [
        SmartmeterSensor(
            config[CONF_USERNAME], config[CONF_PASSWORD], zp["zaehlpunktnummer"]
        )
        for zp in config[CONF_ZAEHLPUNKTE]
    ]
    async_add_entities(sensors, update_before_add=True)


async def async_setup_platform(
    hass: HomeAssistantType,  # pylint: disable=unused-argument
    config: ConfigType,
    async_add_entities: collections.abc.Callable,
    discovery_info: Optional[
        DiscoveryInfoType
    ] = None,  # pylint: disable=unused-argument
) -> None:
    """Set up the sensor platform by adding it into configuration.yaml"""
    sensor = SmartmeterSensor(
        config[CONF_USERNAME], config[CONF_PASSWORD], config[CONF_DEVICE_ID]
    )
    async_add_entities([sensor], update_before_add=True)


class SmartmeterSensor(SensorEntity):
    """
    Representation of a Wiener Smartmeter sensor
    for measuring total increasing energy consumption for a specific zaehlpunkt
    """

    def __init__(self, username: str, password: str, zaehlpunkt: str) -> None:
        super().__init__()
        self.username = username
        self.password = password
        self.zaehlpunkt = zaehlpunkt

        self._attr_native_value = int
        self._attr_extra_state_attributes = {}
        self._attr_name = zaehlpunkt
        self._attr_icon = "mdi:flash"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
        self._attr_unit_of_measurement = ENERGY_KILO_WATT_HOUR

        self.attrs: dict[str, Any] = {}
        self._name: str = zaehlpunkt
        self._state: int = None
        self._available: bool = True
        self._updatets: str = None

    @property
    def icon(self) -> str:
        """
        Return icon
        """
        return self._attr_icon

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        if "label" in self._attr_extra_state_attributes:
            return self._attr_extra_state_attributes["label"]
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return self.zaehlpunkt

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def state(self) -> Optional[str]:  # pylint: disable=overridden-final-method
        return self._state

    async def get_zaehlpunkt(self, smartmeter: Smartmeter) -> dict[str, str]:
        """
        asynchronously get and parse /zaehlpunkt response
        Returns response already sanitzied of the specified zahlpunkt in ctor
        """
        zps = await self.hass.async_add_executor_job(smartmeter.zaehlpunkte)
        if zps is None or len(zps) == 0:
            raise RuntimeError(f"Cannot access Zaehlpunkt {self.zaehlpunkt}")

        zaehlpunkt = [
            z for z in zps[0]["zaehlpunkte"] if z["zaehlpunktnummer"] == self.zaehlpunkt
        ]
        if len(zaehlpunkt) == 0:
            raise RuntimeError(f"Zaehlpunkt {self.zaehlpunkt} not found")
        else:
            return (
                translate_dict(zaehlpunkt[0], ATTRS_ZAEHLPUNKTE_CALL)
                if len(zaehlpunkt) > 0
                else None
            )

    async def get_daily_consumption(self, smartmeter: Smartmeter, date: datetime):
        """
        asynchronously get adn parse /tages_verbrauch response
        Returns response already sanitzied of the specified zahlpunkt in ctor
        """
        response = await self.hass.async_add_executor_job(
            smartmeter.tages_verbrauch, date, self.zaehlpunkt
        )
        if "Exception" in response:
            raise RuntimeError("Cannot access daily consumption: ", response)
        else:
            return response

    async def get_welcome(self, smartmeter: Smartmeter) -> dict[str, str]:
        """
        asynchronously get adn parse /welcome response
        Returns response already sanitzied of the specified zahlpunkt in ctor
        """
        response = await self.hass.async_add_executor_job(smartmeter.welcome)
        if "Exception" in response:
            raise RuntimeError("Cannot access welcome: ", response)
        else:
            return translate_dict(response, ATTRS_WELCOME_CALL)

    def parse_quarterly_consumption_response(self, response):
        """
        Parse and aggregate quarter-hourly consumption
        """
        data = []
        if "values" not in response:
            return None
        values = response["values"]

        sum_consumption = 0
        for value in values:
            timestamp = value["timestamp"]
            quarter_hourly_data = {}
            quarter_hourly_data["utc"] = timestamp
            usage = value["value"]
            if usage is not None:
                sum_consumption += usage

            quarter_hourly_data["usage"] = usage
            data.append(quarter_hourly_data)
        self._state = sum_consumption
        return data

    def is_active(self, zaehlpunkt_response: dict) -> bool:
        """
        returns active status of smartmeter, according to zaehlpunkt response
        """
        return (
            not ("active" in zaehlpunkt_response) or zaehlpunkt_response["active"]
        ) or (
            not ("smartMeterReady" in zaehlpunkt_response)
            or zaehlpunkt_response["smartMeterReady"]
        )

    async def async_update(self):
        """
        update sensor
        """
        try:
            smartmeter = Smartmeter(self.username, self.password)
            await self.hass.async_add_executor_job(smartmeter.login)
            zaehlpunkt = await self.get_zaehlpunkt(smartmeter)
            self._attr_extra_state_attributes = zaehlpunkt

            # TODO: find out how to use quarterly data in another sensor
            #       wiener smartmeter does not expose them quarterly, but daily :/
            # self.attrs = self.parse_quarterly_consumption_response(response)
            if self.is_active(zaehlpunkt):
                welcome = await self.get_welcome(smartmeter)
                # if zaehlpunkt is conincidentally the one returned by /welcome
                if (
                    "zaehlpunkt" in welcome
                    and welcome["zaehlpunkt"] == self.zaehlpunkt
                    and "lastValue" in welcome
                ):
                    if (
                        welcome["lastValue"] is None
                        or self._state != welcome["lastValue"]
                    ):
                        self._state = welcome["lastValue"] / 1000
                else:
                    # if not, we'll have to guesstimate (because api is shitty pomfritty)
                    # for that zaehlpunkt
                    yesterdays_consumption = await self.get_daily_consumption(
                        smartmeter, before(today())
                    )
                    if (
                        "values" in yesterdays_consumption
                        and "statistics" in yesterdays_consumption
                    ):
                        avg = yesterdays_consumption["statistics"]["average"]
                        yesterdays_sum = sum(
                            (
                                y["value"] if y["value"] is not None else avg
                                for y in yesterdays_consumption["values"]
                            )
                        )
                        if yesterdays_sum > 0:
                            self._state = yesterdays_sum
                    else:
                        _LOGGER.error("Unable to load consumption")
                        _LOGGER.error(
                            "Please file an issue with this error and \
                            (anonymized) payload in github %s %s",
                            welcome,
                            yesterdays_consumption,
                        )
                        return
            self._available = True
            self._updatets = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        except RuntimeError:
            self._available = False
            _LOGGER.exception("Error retrieving data from smart meter api")
