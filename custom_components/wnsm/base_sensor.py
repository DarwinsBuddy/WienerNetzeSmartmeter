import logging
from abc import ABC
from datetime import datetime

from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
    SensorEntity,
    ENTITY_ID_FORMAT
)
from homeassistant.const import UnitOfEnergy
from homeassistant.util import slugify

from .api import Smartmeter
from .const import (
    ATTRS_BASEINFORMATION_CALL,
    ATTRS_CONSUMPTIONS_CALL,
    ATTRS_METERREADINGS_CALL,
    ATTRS_ZAEHLPUNKTE_CALL,
    ATTRS_VERBRAUCH_CALL,
    ATTRS_HISTORIC_DATA,
)
from .utils import translate_dict

_LOGGER = logging.getLogger(__name__)


class BaseSensor(SensorEntity, ABC):
    """
    Representation of a Wiener Smartmeter sensor
    for measuring total increasing energy consumption for a specific zaehlpunkt
    """

    def _icon(self) -> str:
        return "mdi:flash"

    def __init__(self, username: str, password: str, zaehlpunkt: str) -> None:
        super().__init__()
        self.username = username
        self.password = password
        self.zaehlpunkt = zaehlpunkt

        self._attr_native_value = int
        self._attr_extra_state_attributes = {}
        self._attr_name = zaehlpunkt
        self._attr_icon = self._icon()
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

        self.attrs: dict[str, Any] = {}
        self._name: str = zaehlpunkt
        self._state: int | str | None = None
        self._available: bool = True
        self._updatets: str | None = None

    @property
    def _id(self):
        return ENTITY_ID_FORMAT.format(slugify(self._name).lower())

    @property
    def icon(self) -> str:
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
        if zps is not None and isinstance(zps, list) and len(zps) > 0 and "zaehlpunkte" in zps[0]:
            zaehlpunkt = [
                z for z in zps[0]["zaehlpunkte"] if z["zaehlpunktnummer"] == self.zaehlpunkt
            ]
        else:
            zaehlpunkt = []
        
        if len(zaehlpunkt) == 0:
            raise RuntimeError(f"Zaehlpunkt {self.zaehlpunkt} not found")

        return (
            translate_dict(zaehlpunkt[0], ATTRS_ZAEHLPUNKTE_CALL)
            if len(zaehlpunkt) > 0
            else None
        )

    async def get_consumption(self, smartmeter: Smartmeter, start_date: datetime):
        """Return 24h of hourly consumption starting from a date"""
        response = await self.hass.async_add_executor_job(
            smartmeter.verbrauch, start_date, self.zaehlpunkt
        )
        if "Exception" in response:
            raise RuntimeError(f"Cannot access daily consumption: {response}")

        return translate_dict(response, ATTRS_VERBRAUCH_CALL)

    async def get_historic_data(self, smartmeter: Smartmeter):
        """Return three years of historic quarter-hourly data"""
        response = await self.hass.async_add_executor_job(
            smartmeter.historical_data, self.zaehlpunkt,
        )
        if "Exception" in response:
            raise RuntimeError(f"Cannot access historic data: {response}")
        _LOGGER.debug(f"Raw historical data: {response}")
        return translate_dict(response, ATTRS_HISTORIC_DATA)

    async def get_base_information(self, smartmeter: Smartmeter) -> dict[str, str]:
        """
        asynchronously get and parse /baseInformation response
        Returns response already sanitized of the specified zaehlpunkt in ctor
        """
        response = await self.hass.async_add_executor_job(smartmeter.base_information)
        if "Exception" in response:
            raise RuntimeError("Cannot access /baseInformation: ", response)
        return translate_dict(response, ATTRS_BASEINFORMATION_CALL)

    async def get_consumptions(self, smartmeter: Smartmeter) -> dict[str, str]:
        """
        asynchronously get and parse /consumptions response
        Returns response already sanitized of the specified zaehlpunkt in ctor
        """
        response = await self.hass.async_add_executor_job(smartmeter.consumptions)
        if "Exception" in response:
            raise RuntimeError("Cannot access /consumptions: ", response)
        return translate_dict(response, ATTRS_CONSUMPTIONS_CALL)

    async def get_meter_readings(self, smartmeter: Smartmeter) -> dict[str, any]:
        """
        asynchronously get and parse /meterReadings response
        Returns response already sanitized of the specified zaehlpunkt in ctor
        """
        response = await self.hass.async_add_executor_job(smartmeter.meter_readings)
        if "Exception" in response:
            raise RuntimeError("Cannot access /meterReadings: ", response)
        return translate_dict(response, ATTRS_METERREADINGS_CALL)

    @staticmethod
    def is_active(zaehlpunkt_response: dict) -> bool:
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
        pass
