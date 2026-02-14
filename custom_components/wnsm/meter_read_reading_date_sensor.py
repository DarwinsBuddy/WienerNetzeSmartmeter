import logging
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.util import dt as dt_util

from .base_sensor import WNSMBaseSensor
from .const import DEFAULT_SCAN_INTERVAL_MINUTES
from .meter_read_logic import async_get_latest_meter_read_payload

_LOGGER = logging.getLogger(__name__)


class WNSMMeterReadReadingDateSensor(WNSMBaseSensor):
    """Expose METER_READ reading_date as dedicated timestamp sensor."""

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

        self._attr_name = f"{zaehlpunkt} Meter Read Reading Date"
        self._attr_icon = "mdi:calendar-clock"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_native_value: datetime | None = None
        self._attr_extra_state_attributes = {}

        self._available: bool = True
        self._attr_suggested_update_interval = scan_interval

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return f"{self.zaehlpunkt}_meter_read_reading_date"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    async def async_update(self):
        """Update sensor."""
        try:
            async_smartmeter = self._get_async_smartmeter()
            await async_smartmeter.login()
            zaehlpunkt_response = await async_smartmeter.get_zaehlpunkt(self.zaehlpunkt)

            if async_smartmeter.is_active(zaehlpunkt_response):
                meter_reading, payload_attributes = await async_get_latest_meter_read_payload(
                    async_smartmeter,
                    self.zaehlpunkt,
                    zaehlpunkt_response,
                )
                self._attr_extra_state_attributes = payload_attributes

                reading_date_iso = payload_attributes.get("reading_date")
                if reading_date_iso is not None and meter_reading is not None:
                    normalized_reading_date = dt_util.parse_datetime(reading_date_iso)
                    if normalized_reading_date is None:
                        _LOGGER.debug(
                            "Could not parse METER_READ reading_date for %s: %s",
                            self.zaehlpunkt,
                            reading_date_iso,
                        )
                    else:
                        if normalized_reading_date.tzinfo is None:
                            normalized_reading_date = normalized_reading_date.replace(tzinfo=dt_util.UTC)
                        self._attr_native_value = normalized_reading_date
                        self._attr_extra_state_attributes["reading_date"] = normalized_reading_date.isoformat()
                else:
                    _LOGGER.debug(
                        "No usable METER_READ reading_date returned for %s", self.zaehlpunkt
                    )

            self._available = True
        except TimeoutError as e:
            self._available = False
            _LOGGER.warning("Error retrieving meter-read reading date from smart meter api - Timeout: %s", e)
        except RuntimeError as e:
            self._available = False
            _LOGGER.exception("Error retrieving meter-read reading date from smart meter api - Error: %s", e)
