import logging
from datetime import datetime

from homeassistant.components.sensor import SensorEntity

from .api import Smartmeter
from .base_sensor import BaseSensor
from .utils import before, today

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
                consumptions = await self.get_consumptions(smartmeter)
                base_information = await self.get_base_information(smartmeter)
                meter_readings = await self.get_meter_readings(smartmeter)
                # if zaehlpunkt is coincidentally the one returned by /welcome
                if (
                        "zaehlpunkt" in base_information
                        and base_information["zaehlpunkt"] == self.zaehlpunkt
                        and "lastValue" in meter_readings
                ):
                    if (
                            meter_readings["lastValue"] is None
                            or self._state != meter_readings["lastValue"]
                    ):
                        self._state = meter_readings["lastValue"] / 1000
                else:
                    # if not, we'll have to guesstimate (because api is shitty-pom-fritty)
                    # for that zaehlpunkt
                    yesterdays_consumption = await self.get_consumption_raw(
                        smartmeter, before(today())
                    )
                    if (
                            "values" in yesterdays_consumption
                            and "consumptionAverage" in yesterdays_consumption
                    ):
                        avg = yesterdays_consumption["consumptionAverage"]
                        yesterdays_sum = sum(
                            (
                                y["value"] if y["value"] is not None else avg
                                for y in yesterdays_consumption["values"]
                            )
                        )
                        if yesterdays_sum > 0:
                            self._state = yesterdays_sum
                    else:
                        _LOGGER.error("Unable to load consumption")
                        _LOGGER.error(
                            "Please file an issue with this error and \
                            (anonymized) payload in github %s %s %s %s",
                            base_information,
                            consumptions,
                            meter_readings,
                            yesterdays_consumption,
                        )
                        return
            self._available = True
            self._updatets = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        except TimeoutError as e:
            self._available = False
            _LOGGER.warning("Error retrieving data from smart meter api - Timeout: %s" % e)
        except RuntimeError as e:
            self._available = False
            _LOGGER.exception("Error retrieving data from smart meter api - Error: %s" % e)
