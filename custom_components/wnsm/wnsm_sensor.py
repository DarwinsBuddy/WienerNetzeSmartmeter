import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from homeassistant.components.sensor import (
    ENTITY_ID_FORMAT,
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.util import slugify

from .AsyncSmartmeter import AsyncSmartmeter
from .api.constants import ValueType
from .const import DOMAIN
from .importer import Importer
from .shared_client import async_get_shared_async_smartmeter
from .utils import before, today

_LOGGER = logging.getLogger(__name__)


class WNSMSensorType(Enum):
    CONSUMPTION = "consumption"
    FEED_IN = "feed_in"
    NET_GRID_BALANCE = "net_grid_balance"


GRID_CONSUMPTION_OBIS_CODE = "1-1:1.9.0 P.01"
GRID_CONSUMPTION_OBIS_CODE_ALT = "1-2:1.9.0 P.01"


@dataclass(frozen=True)
class WNSMSensorDefinition:
    name: str
    unique_suffix: str
    meter_reading_obis_codes: tuple[str, ...]
    profile_role_candidates: tuple[str, ...]
    use_statistics_for_state: bool = False
    use_default_meter_reading: bool = True


SENSOR_DEFINITIONS = {
    WNSMSensorType.CONSUMPTION: WNSMSensorDefinition(
        name="Verbrauch",
        unique_suffix="_Verbrauch",
        meter_reading_obis_codes=(),
        profile_role_candidates=("V002", "V001", "V02T"),
    ),
    WNSMSensorType.FEED_IN: WNSMSensorDefinition(
        name="Eigendeckung",
        unique_suffix="_Eigendeckung",
        meter_reading_obis_codes=(),
        profile_role_candidates=("G003", "G03R"),
        use_statistics_for_state=True,
        use_default_meter_reading=False,
    ),
    WNSMSensorType.NET_GRID_BALANCE: WNSMSensorDefinition(
        name="Restnetzbezug",
        unique_suffix="_Restnetzbezug",
        meter_reading_obis_codes=(
            GRID_CONSUMPTION_OBIS_CODE,
            GRID_CONSUMPTION_OBIS_CODE_ALT,
        ),
        profile_role_candidates=("G001", "G01T"),
        use_statistics_for_state=True,
    ),
}


def _resolve_profile_role_match_from_zaehlwerke(
    zaehlwerke_response: dict,
    candidate_roles: tuple[str, ...],
    preferred_granularities: tuple[str, ...] = ("QH", "D"),
) -> tuple[str | None, str | None]:
    profile_matches: set[tuple[str, str | None]] = set()
    for zaehlwerk in zaehlwerke_response.get("zaehlwerke", []):
        for profile in zaehlwerk.get("profiles", []):
            profile_role = profile.get("profileRole")
            if profile_role in candidate_roles:
                profile_matches.add((profile_role, profile.get("granularity")))

    for preferred_granularity in preferred_granularities:
        for candidate_role in candidate_roles:
            match = (candidate_role, preferred_granularity)
            if match in profile_matches:
                return match

    for candidate_role in candidate_roles:
        for profile_role, granularity in profile_matches:
            if profile_role == candidate_role:
                return profile_role, granularity
    return None, None


def _resolve_profile_role_from_zaehlwerke(
    zaehlwerke_response: dict,
    granularity: ValueType,
    candidate_roles: tuple[str, ...],
) -> str | None:
    expected_granularity = "QH" if granularity == ValueType.QUARTER_HOUR else "D"
    profile_role, _ = _resolve_profile_role_match_from_zaehlwerke(
        zaehlwerke_response,
        candidate_roles,
        (expected_granularity,),
    )
    return profile_role


def _build_device_info(zaehlpunkt: str) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, zaehlpunkt)},
        "manufacturer": "Wiener Netze",
        "model": "Smartmeter",
        "name": zaehlpunkt,
    }


class WNSMSensor(SensorEntity):
    def __init__(
        self,
        username: str,
        password: str,
        zaehlpunkt: str,
        sensor_type: WNSMSensorType = WNSMSensorType.CONSUMPTION,
    ) -> None:
        super().__init__()
        self.username = username
        self.password = password
        self.zaehlpunkt = zaehlpunkt
        self.definition = SENSOR_DEFINITIONS[sensor_type]

        self._attr_native_value: int | float | None = None
        self._attr_extra_state_attributes = {}
        self._attr_name = self.definition.name
        self._attr_icon = "mdi:flash"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self.entity_id = ENTITY_ID_FORMAT.format(
            slugify(f"{self.zaehlpunkt}_{self.definition.name}").lower()
        )

        self._name: str = self._attr_name
        self._available: bool = True

    @property
    def icon(self) -> str:
        return self._attr_icon

    @property
    def name(self) -> str:
        return self._name

    @property
    def unique_id(self) -> str:
        return f"{self.zaehlpunkt}{self.definition.unique_suffix}"

    @property
    def device_info(self) -> dict[str, Any]:
        return _build_device_info(self.zaehlpunkt)

    @property
    def available(self) -> bool:
        return self._available

    def granularity(self) -> ValueType:
        return ValueType.from_str(
            self._attr_extra_state_attributes.get("granularity", "QUARTER_HOUR")
        )

    def statistic_id(self) -> str:
        return f"wnsm:{slugify(self.unique_id)}"

    async def _get_meter_reading(
        self,
        async_smartmeter: AsyncSmartmeter,
        reading_date,
    ) -> float | None:
        if (
            len(self.definition.meter_reading_obis_codes) == 0
            and self.definition.use_default_meter_reading
        ):
            return await async_smartmeter.get_meter_reading_from_historic_data(
                self.zaehlpunkt,
                reading_date,
                datetime.now(),
            )
        if len(self.definition.meter_reading_obis_codes) == 0:
            return None
        for obis_code in self.definition.meter_reading_obis_codes:
            try:
                meter_reading = await async_smartmeter.get_meter_reading_from_historic_data(
                    self.zaehlpunkt,
                    reading_date,
                    datetime.now(),
                    obis_code,
                )
                if meter_reading is not None:
                    return meter_reading
            except Exception as err:
                _LOGGER.debug(
                    "Could not fetch meter reading for %s with OBIS %s: %s",
                    self.unique_id,
                    obis_code,
                    err,
                )
        return None

    async def _resolve_profile_role(
        self,
        async_smartmeter: AsyncSmartmeter,
        customer_id: str,
    ) -> str | None:
        zaehlwerke_response = await async_smartmeter.get_zaehlpunkt_zaehlwerke(
            customer_id,
            self.zaehlpunkt,
        )
        return _resolve_profile_role_from_zaehlwerke(
            zaehlwerke_response,
            self.granularity(),
            self.definition.profile_role_candidates,
        )

    async def async_update(self):
        try:
            resolved_value = False
            async_smartmeter = await async_get_shared_async_smartmeter(
                self.hass,
                self.username,
                self.password,
            )
            await async_smartmeter.login()
            zaehlpunkt_response = await async_smartmeter.get_zaehlpunkt(self.zaehlpunkt)
            self._attr_extra_state_attributes = zaehlpunkt_response

            if async_smartmeter.is_active(zaehlpunkt_response):
                customer_id = zaehlpunkt_response.get("customerId")
                profile_role = await self._resolve_profile_role(
                    async_smartmeter,
                    customer_id,
                )
                importer = Importer(
                    self.hass,
                    async_smartmeter,
                    self.zaehlpunkt,
                    self.unit_of_measurement,
                    self.granularity(),
                    statistic_id=self.statistic_id(),
                    statistic_name=self.name,
                    customer_id=customer_id,
                    profile_role=profile_role,
                )
                reading_dates = [before(today(), 1), before(today(), 2)]
                has_meter_reading = False
                for reading_date in reading_dates:
                    meter_reading = await self._get_meter_reading(
                        async_smartmeter,
                        reading_date,
                    )
                    if meter_reading is not None:
                        has_meter_reading = True
                        self._attr_native_value = meter_reading
                        resolved_value = True
                await importer.async_import()
                if self.definition.use_statistics_for_state or not has_meter_reading:
                    imported_sum = await importer.async_get_last_sum()
                    if imported_sum is not None:
                        self._attr_native_value = imported_sum
                        resolved_value = True
                elif has_meter_reading:
                    resolved_value = True

            if not resolved_value:
                self._attr_native_value = None
            self._available = resolved_value
        except TimeoutError as e:
            self._available = False
            _LOGGER.warning(
                "Error retrieving data from smart meter api - Timeout: %s" % e
            )
        except Exception as e:
            self._available = False
            _LOGGER.exception(
                "Error retrieving data from smart meter api - Error: %s" % e
            )
