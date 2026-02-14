import logging
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.exceptions import HomeAssistantError

from .api.constants import ValueType
from .base_sensor import WNSMBaseSensor
from .const import DEFAULT_SCAN_INTERVAL_MINUTES
from .day_processing import latest_two_day_points
from .day_statistics_importer import DayStatisticsImporter
from .measurement_attributes import set_messwert_attributes
from .utils import before, build_reading_date_attributes, today

_LOGGER = logging.getLogger(__name__)


class WNSMDailySensor(WNSMBaseSensor):
    """Representation of a daily consumption sensor."""

    def __init__(
        self,
        async_smartmeter,
        username: str,
        password: str,
        zaehlpunkt: str,
        enable_day_statistics_import: bool = False,
        scan_interval: timedelta = timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES),
    ) -> None:
        super().__init__(async_smartmeter, username, password)
        self.zaehlpunkt = zaehlpunkt
        self._enable_day_statistics_import = enable_day_statistics_import

        self._attr_native_value: int | float | None = None
        self._attr_name = f"{zaehlpunkt} Day"
        self._attr_icon = "mdi:calendar-today"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_extra_state_attributes = {}

        self._available: bool = True
        self._updatets: str | None = None
        self._attr_suggested_update_interval = scan_interval

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._attr_name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return f"{self.zaehlpunkt}_day"

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
            _, self._attr_extra_state_attributes = build_reading_date_attributes(
                zaehlpunkt_response
            )
            if async_smartmeter.is_active(zaehlpunkt_response):
                start = before(today(), 1)
                end = today()
                messwerte = await async_smartmeter.get_historic_data(
                    self.zaehlpunkt,
                    start,
                    end,
                    ValueType.DAY,
                )

                latest_two_points = latest_two_day_points(messwerte)
                set_messwert_attributes(
                    self._attr_extra_state_attributes,
                    [point.value_kwh for point in latest_two_points],
                )

                latest = latest_two_points[0] if latest_two_points else None
                if latest is not None:
                    self._attr_native_value = latest.value_kwh
                    self._attr_extra_state_attributes["reading_date"] = latest.reading_date
                else:
                    _LOGGER.debug("No usable DAY values returned for %s", self.zaehlpunkt)

                if self._enable_day_statistics_import:
                    importer = DayStatisticsImporter(self.hass, async_smartmeter, self.zaehlpunkt)
                    try:
                        await importer.async_import(start, end)
                    except Exception as e:  # pylint: disable=broad-except
                        _LOGGER.exception(
                            "Error importing day statistics for %s - Error: %s",
                            self.zaehlpunkt,
                            e,
                        )
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
            _LOGGER.exception("Error importing day statistics - Error: %s", e)
