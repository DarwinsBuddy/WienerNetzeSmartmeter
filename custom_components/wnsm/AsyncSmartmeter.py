import asyncio
import logging
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant

from .api import Smartmeter
from .api.constants import ValueType
from .api.errors import SmartmeterConnectionError
from .const import (
    ATTRS_BASEINFORMATION_CALL,
    ATTRS_BEWEGUNGSDATEN,
    ATTRS_CONSUMPTIONS_CALL,
    ATTRS_HISTORIC_DATA,
    ATTRS_METERREADINGS_CALL,
    ATTRS_VERBRAUCH_CALL,
    ATTRS_ZAEHLPUNKTE_CALL,
)
from .utils import translate_dict

_LOGGER = logging.getLogger(__name__)


class AsyncSmartmeter:
    """Async wrapper around Smartmeter API client with reauth support."""

    def __init__(self, hass: HomeAssistant, smartmeter: Smartmeter | None = None):
        self.hass = hass
        self.smartmeter = smartmeter
        self.login_lock = asyncio.Lock()

    async def login(self):
        """Ensure authentication is valid."""
        async with self.login_lock:
            return await self.hass.async_add_executor_job(self.smartmeter.login)

    @staticmethod
    def _response_has_exception(response: Any) -> bool:
        return isinstance(response, dict) and "Exception" in response

    @staticmethod
    def _is_unauthorized_response(response: Any) -> bool:
        if not isinstance(response, dict):
            return False
        status = response.get("status") or response.get("statusCode")
        if status == 401:
            return True
        exception_message = str(response.get("Exception", ""))
        return "401" in exception_message or "unauthorized" in exception_message.lower()

    async def _call_with_reauth(self, method, *args):
        """Run Smartmeter API call and retry once after reauth if needed."""
        try:
            response = await self.hass.async_add_executor_job(method, *args)
        except SmartmeterConnectionError:
            await self.login()
            response = await self.hass.async_add_executor_job(method, *args)

        if self._is_unauthorized_response(response):
            await self.login()
            response = await self.hass.async_add_executor_job(method, *args)

        return response

    async def get_meter_readings(self) -> dict[str, Any]:
        """Asynchronously get and parse /meterReadings response."""
        response = await self._call_with_reauth(self.smartmeter.historical_data)
        if self._response_has_exception(response):
            raise RuntimeError("Cannot access /meterReadings", response)
        return translate_dict(response, ATTRS_METERREADINGS_CALL)

    async def get_base_information(self) -> dict[str, str]:
        """Asynchronously get and parse /baseInformation response."""
        response = await self._call_with_reauth(self.smartmeter.base_information)
        if self._response_has_exception(response):
            raise RuntimeError("Cannot access /baseInformation", response)
        return translate_dict(response, ATTRS_BASEINFORMATION_CALL)

    def contracts2zaehlpunkte(self, contracts: dict, zaehlpunkt: str) -> list[dict]:
        zaehlpunkte = []
        if contracts is not None and isinstance(contracts, list) and len(contracts) > 0:
            for contract in contracts:
                if "zaehlpunkte" in contract:
                    geschaeftspartner = contract["geschaeftspartner"] if "geschaeftspartner" in contract else None
                    zaehlpunkte += [
                        {**z, "geschaeftspartner": geschaeftspartner}
                        for z in contract["zaehlpunkte"]
                        if z["zaehlpunktnummer"] == zaehlpunkt
                    ]
        else:
            raise RuntimeError(f"Cannot access Zaehlpunkt {zaehlpunkt}")
        return zaehlpunkte

    async def get_zaehlpunkt(self, zaehlpunkt: str) -> dict[str, str]:
        """Asynchronously get and parse /zaehlpunkt response."""
        contracts = await self._call_with_reauth(self.smartmeter.zaehlpunkte)
        zaehlpunkte = self.contracts2zaehlpunkte(contracts, zaehlpunkt)
        zp = [z for z in zaehlpunkte if z["zaehlpunktnummer"] == zaehlpunkt]
        if len(zp) == 0:
            raise RuntimeError(f"Zaehlpunkt {zaehlpunkt} not found")

        return translate_dict(zp[0], ATTRS_ZAEHLPUNKTE_CALL) if len(zp) > 0 else None

    async def get_consumption(self, customer_id: str, zaehlpunkt: str, start_date: datetime):
        """Return 24h of hourly consumption starting from a date."""
        response = await self._call_with_reauth(
            self.smartmeter.verbrauch,
            customer_id,
            zaehlpunkt,
            start_date,
        )
        if self._response_has_exception(response):
            raise RuntimeError(f"Cannot access daily consumption: {response}")

        return translate_dict(response, ATTRS_VERBRAUCH_CALL)

    async def get_consumption_raw(self, customer_id: str, zaehlpunkt: str, start_date: datetime):
        """Return daily consumptions from the given start date until today."""
        response = await self._call_with_reauth(
            self.smartmeter.verbrauchRaw,
            customer_id,
            zaehlpunkt,
            start_date,
        )
        if self._response_has_exception(response):
            raise RuntimeError(f"Cannot access daily consumption: {response}")

        return translate_dict(response, ATTRS_VERBRAUCH_CALL)

    async def get_historic_data(
        self,
        zaehlpunkt: str,
        date_from: datetime = None,
        date_to: datetime = None,
        granularity: ValueType = ValueType.QUARTER_HOUR,
    ):
        """Return historic data."""
        response = await self._call_with_reauth(
            self.smartmeter.historical_data,
            zaehlpunkt,
            date_from,
            date_to,
            granularity,
        )
        if self._response_has_exception(response):
            raise RuntimeError(f"Cannot access historic data: {response}")
        _LOGGER.debug("Raw historical data: %s", response)
        return translate_dict(response, ATTRS_HISTORIC_DATA)

    async def get_meter_reading_from_historic_data(
        self,
        zaehlpunkt: str,
        start_date: datetime,
        end_date: datetime,
    ) -> float:
        """Return daily meter readings from the given start date until today."""
        response = await self._call_with_reauth(
            self.smartmeter.historical_data,
            zaehlpunkt,
            start_date,
            end_date,
            ValueType.METER_READ,
        )
        if self._response_has_exception(response):
            raise RuntimeError(f"Cannot access historic data: {response}")
        _LOGGER.debug("Raw historical data: %s", response)
        meter_readings = translate_dict(response, ATTRS_HISTORIC_DATA)
        if "values" in meter_readings and all("messwert" in messwert for messwert in meter_readings["values"]) and len(meter_readings["values"]) > 0:
            return meter_readings["values"][0]["messwert"] / 1000
        return None

    @staticmethod
    def is_active(zaehlpunkt_response: dict) -> bool:
        """Return active status according to zaehlpunkt response."""
        is_active = "active" not in zaehlpunkt_response or zaehlpunkt_response["active"]
        is_smartmeter_ready = (
            "smartMeterReady" not in zaehlpunkt_response
            or zaehlpunkt_response["smartMeterReady"]
        )
        return is_active and is_smartmeter_ready

    async def get_bewegungsdaten(
        self,
        zaehlpunkt: str,
        start: datetime = None,
        end: datetime = None,
        granularity: ValueType = ValueType.QUARTER_HOUR,
    ):
        """Return historic bewegungsdaten."""
        response = await self._call_with_reauth(
            self.smartmeter.bewegungsdaten,
            zaehlpunkt,
            start,
            end,
            granularity,
        )
        if self._response_has_exception(response):
            raise RuntimeError(f"Cannot access bewegungsdaten: {response}")
        _LOGGER.debug("Raw bewegungsdaten: %s", response)
        return translate_dict(response, ATTRS_BEWEGUNGSDATEN)

    async def get_consumptions(self) -> dict[str, str]:
        """Asynchronously get and parse /consumptions response."""
        response = await self._call_with_reauth(self.smartmeter.consumptions)
        if self._response_has_exception(response):
            raise RuntimeError("Cannot access /consumptions", response)
        return translate_dict(response, ATTRS_CONSUMPTIONS_CALL)
