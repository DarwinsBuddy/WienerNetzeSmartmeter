import logging
from warnings import deprecated

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import UnitOfEnergy

from .wnsm_sensor import WNSMSensor

_LOGGER = logging.getLogger(__name__)


@deprecated("Remove this sensor from your configuration.")
class StatisticsSensor(WNSMSensor, SensorEntity):

    def __init__(self, username: str, password: str, zaehlpunkt: str) -> None:
        super().__init__(username, password, zaehlpunkt)
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    @staticmethod
    def statistics(s: str) -> str:
        return f'{s}_statistics'

    @property
    def icon(self) -> str:
        return "mdi:meter-electric-outline"

    @property
    def _id(self) -> str:
        return StatisticsSensor.statistics(super()._id)

    @property
    def name(self) -> str:
        return StatisticsSensor.statistics(super().name)

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return StatisticsSensor.statistics(super().unique_id)

    async def async_update(self):
        """
        disable sensor
        """
        self._available = False
        _LOGGER.warning("StatisticsSensor disabled. Please remove it from your configuration.")