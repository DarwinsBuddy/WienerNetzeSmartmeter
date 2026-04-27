import asyncio
import logging
from asyncio import Future
from datetime import datetime

from homeassistant.core import HomeAssistant

from .api import Smartmeter
from .api.constants import ValueType
from .const import ATTRS_BEWEGUNGSDATEN, ATTRS_HISTORIC_DATA, ATTRS_ZAEHLPUNKTE_CALL
from .utils import translate_dict

_LOGGER = logging.getLogger(__name__)

class AsyncSmartmeter:

    def __init__(self, hass: HomeAssistant, smartmeter: Smartmeter = None):
        self.hass = hass
        self.smartmeter = smartmeter
        self.login_lock = asyncio.Lock()
        self.request_lock = asyncio.Lock()

    async def _async_call(self, func, *args):
        async with self.request_lock:
            return await self.hass.async_add_executor_job(func, *args)

    async def login(self) -> Future:
        async with self.login_lock:
            return await self._async_call(self.smartmeter.login)

    def contracts2zaehlpunkte(self, contracts: dict, zaehlpunkt: str) -> list[dict]:
        zaehlpunkte = []
        if contracts is not None and isinstance(contracts, list) and len(contracts) > 0:
            for contract in contracts:
                if "zaehlpunkte" in contract:
                    geschaeftspartner = contract["geschaeftspartner"] if "geschaeftspartner" in contract else None
                    zaehlpunkte += [
                        {**z, "geschaeftspartner": geschaeftspartner} for z in contract["zaehlpunkte"] if z["zaehlpunktnummer"] == zaehlpunkt
                    ]
        else:
            raise RuntimeError(f"Cannot access Zaehlpunkt {zaehlpunkt}")
        return zaehlpunkte

    async def get_zaehlpunkt(self, zaehlpunkt: str) -> dict[str, str]:
        contracts = await self._async_call(self.smartmeter.zaehlpunkte)
        zaehlpunkte = self.contracts2zaehlpunkte(contracts, zaehlpunkt)
        zp = [z for z in zaehlpunkte if z["zaehlpunktnummer"] == zaehlpunkt]
        if len(zp) == 0:
            raise RuntimeError(f"Zaehlpunkt {zaehlpunkt} not found")

        return (
            translate_dict(zp[0], ATTRS_ZAEHLPUNKTE_CALL)
            if len(zp) > 0
            else None
        )

    async def get_zaehlpunkt_zaehlwerke(self, customer_id: str, zaehlpunkt: str) -> dict:
        response = await self._async_call(
            self.smartmeter.zaehlpunkt_zaehlwerke,
            customer_id,
            zaehlpunkt,
        )
        if "Exception" in response:
            raise RuntimeError(f"Cannot access zaehlwerke: {response}")
        return response

    async def get_bewegungsdaten_by_profile_role(self, customer_id: str, zaehlpunkt: str, profile_role: str, start: datetime = None, end: datetime = None, aggregat: str = "NONE"):
        response = await self._async_call(
            self.smartmeter.bewegungsdaten_by_profile_role,
            customer_id,
            zaehlpunkt,
            profile_role,
            start,
            end,
            aggregat,
        )
        if "Exception" in response:
            raise RuntimeError(f"Cannot access bewegungsdaten: {response}")
        descriptor = response.get("descriptor", {})
        _LOGGER.debug(
            "Raw bewegungsdaten for role %s: unit=%s values=%s granularity=%s",
            profile_role,
            descriptor.get("einheit"),
            len(response.get("values", [])),
            descriptor.get("granularitaet"),
        )
        return translate_dict(response, ATTRS_BEWEGUNGSDATEN)

    async def get_meter_reading_from_historic_data(self, zaehlpunkt: str, start_date: datetime, end_date: datetime, obis_code: str = None) -> float:
        response = await self._async_call(
            self.smartmeter.historical_data,
            zaehlpunkt,
            start_date,
            end_date,
            ValueType.METER_READ,
            obis_code,
        )
        if "Exception" in response:
            raise RuntimeError(f"Cannot access historic data: {response}")
        _LOGGER.debug("Raw historical data values=%s", len(response.get("values", [])))
        meter_readings = translate_dict(response, ATTRS_HISTORIC_DATA)
        if "values" in meter_readings and all("messwert" in messwert for messwert in meter_readings['values']) and len(meter_readings['values']) > 0:
            return meter_readings['values'][0]['messwert'] / 1000

    @staticmethod
    def is_active(zaehlpunkt_response: dict) -> bool:
        return (
                "active" not in zaehlpunkt_response or zaehlpunkt_response["active"]
        ) or (
                "smartMeterReady" not in zaehlpunkt_response
                or zaehlpunkt_response["smartMeterReady"]
        )
