"""WienerNetze Smartmeter sensor platform"""
import logging
from decimal import Decimal
from datetime import timedelta, datetime, timezone
from typing import Any, Callable, Dict, Optional

import voluptuous as vol
from homeassistant import core, config_entries

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICE_ID,
    DEVICE_CLASS_ENERGY,
    ENERGY_KILO_WATT_HOUR,
)
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    get_last_statistics,
    async_import_statistics,
)
from homeassistant.core import DOMAIN
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)
from homeassistant.util import dt as dt_util

from custom_components.wnsm.api import Smartmeter
from custom_components.wnsm.const import (
    ATTRS_WELCOME_CALL,
    ATTRS_ZAEHLPUNKTE_CALL,
    CONF_ZAEHLPUNKTE,
)
from custom_components.wnsm.utils import before, today, translate_dict

_LOGGER = logging.getLogger(__name__)
# Time between updating data from Wiener Netze
SCAN_INTERVAL = timedelta(minutes=15)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_DEVICE_ID): cv.string,
    }
)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    """Setup sensors from a config entry created in the integrations UI."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    sensors = [
        SmartmeterSensor(
            config[CONF_USERNAME], config[CONF_PASSWORD], zp["zaehlpunktnummer"]
        )
        for zp in config[CONF_ZAEHLPUNKTE]
    ]
    async_add_entities(sensors, update_before_add=True)


async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: Callable,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the sensor platform by adding it into configuration.yaml"""
    sensor = SmartmeterSensor(
        config[CONF_USERNAME], config[CONF_PASSWORD], config[CONF_DEVICE_ID]
    )
    async_add_entities([sensor], update_before_add=True)


class SmartmeterSensor(SensorEntity):
    """
    Representation of a Wiener Smartmeter sensor
    for measuring total increasing energy consumption for a specific zaehlpunkt
    """

    def __init__(self, username: str, password: str, zaehlpunkt: str):
        super().__init__()
        self.username = username
        self.password = password
        self.zaehlpunkt = zaehlpunkt

        self._attr_native_value = int
        self._attr_extra_state_attributes = {}
        self._attr_name = zaehlpunkt
        self._attr_icon = "mdi:flash"
        self._attr_device_class = DEVICE_CLASS_ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
        self._attr_unit_of_measurement = ENERGY_KILO_WATT_HOUR

        self.attrs: Dict[str, Any] = {}
        self._name: str | None = zaehlpunkt
        self._state: int | None = None
        self._available: bool = True

    @property
    def icon(self) -> str:
        return self._attr_icon

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        if "label" in self._attr_extra_state_attributes:
            return self._attr_extra_state_attributes["label"]
        else:
            return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return self.zaehlpunkt

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def state(self) -> Optional[str]:
        return self._state

    async def get_zaehlpunkt(self, smartmeter: Smartmeter) -> Dict[str, str]:
        zps = await self.hass.async_add_executor_job(smartmeter.zaehlpunkte)
        if zps is None or len(zps) == 0:
            raise RuntimeError(f"Cannot access Zaehlpunkt {self.zaehlpunkt}")
        else:
            zp = [
                z
                for z in zps[0]["zaehlpunkte"]
                if z["zaehlpunktnummer"] == self.zaehlpunkt
            ]
            if len(zp) == 0:
                raise RuntimeError(f"Zaehlpunkt {self.zaehlpunkt} not found")
            else:
                return (
                    translate_dict(zp[0], ATTRS_ZAEHLPUNKTE_CALL)
                    if len(zp) > 0
                    else None
                )

    async def get_daily_consumption(self, smartmeter: Smartmeter, date: datetime):
        response = await self.hass.async_add_executor_job(
            smartmeter.tages_verbrauch, date, self.zaehlpunkt
        )
        if "Exception" in response:
            raise RuntimeError("Cannot access daily consumption: ", response)
        else:
            return response

    async def get_consumption(self, smartmeter: Smartmeter, start_date: datetime):
        """Return the consumption starting from a date"""
        response = await self.hass.async_add_executor_job(smartmeter.verbrauch, start_date, None, self.zaehlpunkt)
        if "Exception" in response:
            raise RuntimeError("Cannot access daily consumption: ", response)
        return response

    async def get_welcome(self, smartmeter: Smartmeter) -> Dict[str, str]:
        response = await self.hass.async_add_executor_job(smartmeter.welcome)
        if "Exception" in response:
            raise RuntimeError("Cannot access welcome: ", response)
        else:
            return translate_dict(response, ATTRS_WELCOME_CALL)

    def parse_quarterly_consumption_response(self, response):
        data = []
        if "values" not in response:
            return None
        values = response["values"]

        sum = 0
        for v in values:
            ts = v["timestamp"]
            quarter_hourly_data = {}
            quarter_hourly_data["utc"] = ts
            usage = v["value"]
            if usage is not None:
                sum += usage

            quarter_hourly_data["usage"] = usage
            data.append(quarter_hourly_data)
        self._state = sum
        return data

    async def _import_statistics(self, smartmeter: Smartmeter, start: datetime, sum_: Decimal):
        """Import hourly consumption data into the statistics module, using start date and sum"""
        if start.tzinfo is None:
            raise ValueError("start datetime must be timezone-aware!")
        # Have to be sure that full minutes are used. otherwise, the API returns a different
        # interval
        start = start.replace(minute=0, second=0, microsecond=0)

        has_none = False
        statistics = []
        metadata = StatisticMetaData(
            source="recorder",
            statistic_id=f'sensor.{self.unique_id.lower()}',
            name=self.name,
            unit_of_measurement=self._attr_unit_of_measurement,
            has_mean=False,
            has_sum=True,
        )
        _LOGGER.debug(metadata)

        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        _LOGGER.debug(f"Selecting data up to {now}")
        # FIXME: this loop is prone to endless loops, if the API returns something funny...
        # Thus, we add a counter here as well. But there are probably better methods to prevent that
        iterations = 50
        while iterations > 0 and not has_none and start < now:
            _LOGGER.debug(f"Select 24h of Data, using sum={sum_:.3f}, start={start}")
            iterations -= 1
            verbrauch = await self.get_consumption(smartmeter, start)
            _LOGGER.debug(verbrauch)

            # Check if this batch of data is valid and contains hourly statistics:
            if not verbrauch.get('quarter-hour-opt-in'):
                _LOGGER.warning(f"Data starting at {start} does not contain granular data! Opt-in was not set back then.")
                start += timedelta(hours=24)  # Select the next day...
                continue

            if 'values' not in verbrauch:
                _LOGGER.error("No values in API response!")
                continue

            # TODO: What happens on summer-/wintertime change in the statistics?
            for v in verbrauch['values']:
                # Timestamp has to be aware of timezone
                ts = datetime.fromisoformat(v['timestamp'][:-1]).replace(tzinfo=timezone.utc)
                if ts < start:
                    _LOGGER.debug(f"Timestamp from API ({ts}) is less than start time ({start}), ignoring value!")
                    continue
                if ts.minute != 0:
                    _LOGGER.error("Minute of timestamp is non-zero, this must not happen!")
                    return
                if v['value'] is None:
                    # Measurement not yet in the database...
                    # TODO: is it possible that after a None are more values?
                    # If not, we could break as soon as we hit the first None value.
                    has_none = True
                    continue
                elif has_none:
                    _LOGGER.warning("Value is suddenly not None anymore!")
                sum_ += Decimal(v['value'] / 1000.0)  # Convert to kWh, and accumulate
                statistics.append(StatisticData(start=ts, sum=sum_))

                # Set new start date for next batch
                start = ts + timedelta(hours=1)

        _LOGGER.debug(statistics)

        # Import the statistics data
        async_import_statistics(self.hass, metadata, statistics)

    def is_active(self, zp: dict) -> bool:
        return (not ("active" in zp) or zp["active"]) or (
            not ("smartMeterReady" in zp) or zp["smartMeterReady"]
        )

    async def async_update(self):
        try:
            smartmeter = Smartmeter(self.username, self.password)
            await self.hass.async_add_executor_job(smartmeter.login)
            zp = await self.get_zaehlpunkt(smartmeter)
            self._attr_extra_state_attributes = zp

            if not self.is_active(zp):
                _LOGGER.warning("Smartmeter not active...")
                return

            # TODO: why does self.entity_id returns None?
            entity_id = f'sensor.{self.unique_id.lower()}'

            # Get last sum and last date from statistics
            # From
            # https://github.com/DarkC35/ha_linznetz/blob/904f361e760103f900ad93522a0215d348fc83bb/custom_components/linznetz/sensor.py
            # Select one entry from the statistics, convert the units
            last_inserted_stat = await get_instance(self.hass).async_add_executor_job(get_last_statistics, self.hass, 1, entity_id, True)
            _LOGGER.debug(f"Last inserted stat: {last_inserted_stat}")

            if len(last_inserted_stat) == 0 or len(last_inserted_stat[entity_id]) == 0:
                # No previous data

                # FIXME: This seems not to work and after some time you get a negative consumption
                """
                # Let's fetch some initial data we can use...
                welcome = await self.get_welcome(smartmeter)
                _LOGGER.debug(welcome)
                if welcome.get('zaehlpunkt') == self.zaehlpunkt and welcome.get('lastValue') is not None:
                    _LOGGER.debug("Found zählpunkt and it has a last reading")
                    # If this is the case, we can get the last available zählerstand as a baseline and
                    # then query the statistics after that
                    state = Decimal(welcome['lastValue'] / 1000.0)
                    start = datetime.fromisoformat(welcome['lastReading'][:-1])
                    # To get better stats, we subtract the consumption from yesterday and the day
                    # before that, so we can collect the hourly stats for the last two days:
                    state -= Decimal(welcome['consumptionYesterday'] / 1000.0)
                    state -= Decimal(welcome['consumptionDayBeforeYesterday'] / 1000.0)
                    start -= timedelta(hours=48)

                    # Set the value on the sensor itself and not in the statistics!
                    self._state = state
                    self._updatets = start.strftime("%d.%m.%Y %H:%M:%S")
                else:
                    # Start from scratch
                    _LOGGER.debug("Not previous data found... starting from scratch")
                    # TODO: what would be a sensible date here? usually, the first data is min. of
                    # 24h old...
                    start = before(before())
                """

                # Start from scratch
                _sum = Decimal(0)
                start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=672)  # For testing, use 4 weeks of data
            elif len(last_inserted_stat) == 1 and len(last_inserted_stat[entity_id]) == 1:
                # Previous data found in the statistics table
                _sum = Decimal(last_inserted_stat[entity_id][0]["sum"])
                start = dt_util.parse_datetime(last_inserted_stat[entity_id][0]["start"])

                # FIXME: must we add 1h to the last reading or not? I guess we have to?
                start += timedelta(hours=1)
                _LOGGER.debug(f"Got statistic data: sum={_sum}, start={start} -> {start.tzinfo}")
            else:
                _LOGGER.error("unexpected result of previous stats")
                return

            # Collect hourly data
            await self._import_statistics(smartmeter, start, _sum)

            self._available = True
            self._updatets = start.strftime("%d.%m.%Y %H:%M:%S")
        except RuntimeError:
            self._available = False
            _LOGGER.exception("Error retrieving data from smart meter api.")
