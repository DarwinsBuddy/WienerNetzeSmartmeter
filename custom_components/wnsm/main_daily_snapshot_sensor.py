import logging
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.exceptions import HomeAssistantError

from .base_sensor import WNSMBaseSensor
from .const import DEFAULT_SCAN_INTERVAL_MINUTES
from .main_daily_snapshot_statistics_importer import MainDailySnapshotStatisticsImporter
from .meter_read_logic import async_get_latest_meter_read_payload

_LOGGER = logging.getLogger(__name__)


class WNSMMainDailySnapshotSensor(WNSMBaseSensor):
    """Measurement-style METER_READ snapshot sensor with reading-date aligned statistics."""

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

        self._attr_native_value: int | float | None = None
        self._attr_name = f"{zaehlpunkt} Main Daily Snapshot"
        self._attr_icon = "mdi:flash"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_extra_state_attributes = {}

        self._available: bool = True
        self._updatets: str | None = None
        self._attr_suggested_update_interval = scan_interval

    @property
    def name(self) -> str:
        return self._attr_name

    @property
    def unique_id(self) -> str:
        return f"{self.zaehlpunkt}_main_daily_snapshot"

    @property
    def available(self) -> bool:
        return self._available

    async def async_update(self):
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
                    importer = MainDailySnapshotStatisticsImporter(self.hass, self.zaehlpunkt)
                    await importer.async_import_from_payload(self._attr_extra_state_attributes)
            self._available = True
            self._updatets = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        except TimeoutError as e:
            self._available = False
            _LOGGER.warning("Error retrieving data from smart meter api - Timeout: %s", e)
        except RuntimeError as e:
            self._available = False
            _LOGGER.exception("Error retrieving data from smart meter api - Error: %s", e)
        except HomeAssistantError as e:
            self._available = False
            _LOGGER.exception("Error importing main snapshot statistics - Error: %s", e)
