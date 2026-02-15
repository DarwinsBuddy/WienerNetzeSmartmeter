import logging
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.event import async_track_time_interval

from .AsyncSmartmeter import AsyncSmartmeter
from .api import Smartmeter
from .api.constants import ValueType
from .utils import before, today

_LOGGER = logging.getLogger(__name__)


class WNSMReadingDateSensor(SensorEntity):
    """Representation of a reading date sensor."""

    def __init__(
        self,
        username: str,
        password: str,
        zaehlpunkt: str,
        sensor_suffix: str,
        valuetype: ValueType,
        scan_interval: timedelta | None = None,
    ) -> None:
        super().__init__()
        self.username = username
        self.password = password
        self.zaehlpunkt = zaehlpunkt
        self.valuetype = valuetype
        self._scan_interval = scan_interval
        self._unsub_timer = None

        self._attr_native_value: datetime | None = None
        self._attr_name = f"{zaehlpunkt} {sensor_suffix} Reading Date"
        self._attr_icon = "mdi:calendar-clock"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_unique_id = f"{zaehlpunkt}_{sensor_suffix.lower().replace(' ', '_')}_reading_date"
        self._attr_should_poll = self._scan_interval is None

        self._available: bool = True
        self._updatets: str | None = None
        self._unique_id = self._attr_unique_id

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return self._unique_id

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    async def async_added_to_hass(self) -> None:
        if self._scan_interval:
            self._unsub_timer = async_track_time_interval(
                self.hass,
                self._handle_scheduled_update,
                self._scan_interval,
            )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

    async def _handle_scheduled_update(self, now) -> None:
        await self.async_update()
        self.async_write_ha_state()

    async def async_update(self):
        """Update sensor."""
        try:
            smartmeter = Smartmeter(username=self.username, password=self.password)
            async_smartmeter = AsyncSmartmeter(self.hass, smartmeter)
            await async_smartmeter.login()
            zaehlpunkt_response = await async_smartmeter.get_zaehlpunkt(self.zaehlpunkt)
            if async_smartmeter.is_active(zaehlpunkt_response):
                reading_dates = [before(today(), 1), before(today(), 2)]
                if self.valuetype == ValueType.METER_READ:
                    for reading_date in reading_dates:
                        meter_reading = await async_smartmeter.get_meter_reading_from_historic_data(
                            self.zaehlpunkt,
                            reading_date,
                            datetime.now(),
                        )
                        if meter_reading is not None:
                            self._attr_native_value = reading_date
                            break
                else:
                    messwerte = await async_smartmeter.get_historic_data(
                        self.zaehlpunkt,
                        reading_dates[0],
                        today(),
                        ValueType.DAY,
                    )
                    if messwerte.get("values"):
                        self._attr_native_value = reading_dates[0]
            self._available = True
            self._updatets = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        except TimeoutError as e:
            self._available = False
            _LOGGER.warning("Error retrieving data from smart meter api - Timeout: %s", e)
        except RuntimeError as e:
            self._available = False
            _LOGGER.exception("Error retrieving data from smart meter api - Error: %s", e)
