import logging
from datetime import datetime

from homeassistant.components.sensor import SensorEntity

from .api import Smartmeter
from .base_sensor import BaseSensor
from .utils import before, today, safeget

_LOGGER = logging.getLogger(__name__)


class LiveSensor(BaseSensor, SensorEntity):
    """
    Representation of a Wiener Smartmeter sensor
    for measuring total increasing energy consumption for a specific zaehlpunkt
    """

    def __init__(self, username: str, password: str, zaehlpunkt: str) -> None:
        super().__init__(username, password, zaehlpunkt)

    async def async_update(self):
        """
        update sensor
        """
        try:
            smartmeter = Smartmeter(self.username, self.password)
            await self.hass.async_add_executor_job(smartmeter.login)
            zaehlpunkt = await self.get_zaehlpunkt(smartmeter)
            self._attr_extra_state_attributes = zaehlpunkt

            if self.is_active(zaehlpunkt):
                #Since the update is not exactly at midnight, both yesterday and the day before are tried to make sure a meter reading is returned
                reading_dates = [before(today(),1), before(today(),2)]
                for reading_date in reading_dates:
                    meter_readings = await self.get_meter_reading_from_historic_data(smartmeter,reading_date)
                    if "values" in meter_readings and all("messwert" in messwert for messwert in meter_readings['values']) and len(meter_readings['values'])>0:                        
                        self._state = meter_readings['values'][-1]['messwert']/1000
                        break
                else:
                        _LOGGER.error("Unable to load consumption")
                        _LOGGER.error(
                            "Please file an issue with this error and (anonymized) payload in github %s",
                            meter_readings
                        )
                        return
            self._available = True
            self._updatets = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        except TimeoutError as e:
            self._available = False
            _LOGGER.warning(
                "Error retrieving data from smart meter api - Timeout: %s" % e)
        except RuntimeError as e:
            self._available = False
            _LOGGER.exception(
                "Error retrieving data from smart meter api - Error: %s" % e)