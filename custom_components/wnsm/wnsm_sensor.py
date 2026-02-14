import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
    ENTITY_ID_FORMAT,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.util import slugify

from .api.constants import ValueType
from .base_sensor import WNSMBaseSensor
from .const import DEFAULT_SCAN_INTERVAL_MINUTES
from .importer import Importer
from .meter_read_logic import async_get_latest_meter_read_payload

_LOGGER = logging.getLogger(__name__)


class WNSMSensor(WNSMBaseSensor):
    """Representation of Wiener Smartmeter total energy sensor."""

    def _icon(self) -> str:
        return "mdi:flash"

    def __init__(
        self,
        async_smartmeter,
        username: str,
        password: str,
        zaehlpunkt: str,
        scan_interval: timedelta = timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES),
    ) -> None:
        super().__init__(async_smartmeter, username, password)
        self.zaehlpunkt = zaehlpunkt

        self._attr_native_value: int | float | None = 0
        self._attr_extra_state_attributes = {"raw_api": {}}
        self._attr_name = zaehlpunkt
        self._attr_icon = self._icon()
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

        self.attrs: dict[str, Any] = {}
        self._name: str = zaehlpunkt
        self._available: bool = True
        self._updatets: str | None = None
        self._attr_suggested_update_interval = scan_interval

    @property
    def get_state(self) -> Optional[str]:
        return f"{self._attr_native_value:.3f}"

    @property
    def _id(self):
        return ENTITY_ID_FORMAT.format(slugify(self._name).lower())

    @property
    def icon(self) -> str:
        return self._attr_icon

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return self.zaehlpunkt

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    def granularity(self) -> ValueType:
        return ValueType.from_str(self._attr_extra_state_attributes.get("granularity", "QUARTER_HOUR"))

    async def async_update(self):
        """Update sensor."""
        try:
            async_smartmeter = self._get_async_smartmeter()
            await async_smartmeter.login()
            zaehlpunkt_response = await async_smartmeter.get_zaehlpunkt(self.zaehlpunkt)
            if async_smartmeter.is_active(zaehlpunkt_response):
                meter_reading, self._attr_extra_state_attributes = await async_get_latest_meter_read_payload(
                    async_smartmeter,
                    self.zaehlpunkt,
                    zaehlpunkt_response,
                )
                if meter_reading is not None:
                    self._attr_native_value = meter_reading
                    reading_date = self._attr_extra_state_attributes.get("reading_date")
                    importer = Importer(
                        self.hass,
                        async_smartmeter,
                        self.zaehlpunkt,
                        self.unit_of_measurement,
                        self.granularity(),
                    )
                    await importer.async_import_meter_read(reading_date, meter_reading)
            self._available = True
            self._updatets = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        except TimeoutError as e:
            self._available = False
            _LOGGER.warning("Error retrieving data from smart meter api - Timeout: %s", e)
        except RuntimeError as e:
            self._available = False
            _LOGGER.exception("Error retrieving data from smart meter api - Error: %s", e)
