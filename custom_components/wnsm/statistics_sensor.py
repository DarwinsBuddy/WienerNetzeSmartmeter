import logging

from homeassistant.components.recorder import get_instance
from homeassistant.components.sensor import SensorEntity

from .api import Smartmeter
from .base_sensor import BaseSensor
from .utils import today

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_import_statistics, get_last_statistics,
)
from decimal import Decimal
from homeassistant.util import dt as dt_util
from datetime import timedelta, timezone, datetime
from operator import itemgetter
from collections import defaultdict

_LOGGER = logging.getLogger(__name__)
class StatisticsSensor(BaseSensor, SensorEntity):
    def __init__(self, username: str, password: str, zaehlpunkt: str) -> None:
        super().__init__(username, password, zaehlpunkt)

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
        update sensor
        """

        # Query the statistics database for the last value
        # It is crucial to use get_instance here!
        last_inserted_stat = await get_instance(
            self.hass
        ).async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,  # Get at most one entry
            self._id,  # of this sensor
            True,  # convert the units
            # XXX: since HA core 2022.12 need to specify this:
            {"sum", "state"},  # the fields we want to query (state might be used in the future)
        )
        _LOGGER.debug("Last inserted stat: %s" % last_inserted_stat)

        init_meter = False

        if len(last_inserted_stat) == 0 or len(last_inserted_stat[self._id]) == 0:
            # No previous data - start from scratch
            init_meter = True
        elif len(last_inserted_stat) == 1 and len(last_inserted_stat[self._id]) == 1:
            # Previous data found in the statistics table
            _sum = Decimal(last_inserted_stat[self._id][0]["sum"])
            # The next start is the previous end
            # XXX: since HA core 2022.12, we get a datetime and not a str...
            # XXX: since HA core 2023.03, we get a float and not a datetime...
            start = last_inserted_stat[self._id][0]["end"]
            if isinstance(start, (int, float)):
                start = dt_util.utc_from_timestamp(start)
            if isinstance(start, str):
                start = dt_util.parse_datetime(start)

            if not isinstance(start, datetime):
                _LOGGER.error("HA core decided to change the return type AGAIN! "
                              "Please open a bug report. "
                              "Additional Information: %s Type: %s",
                              last_inserted_stat,
                              type(last_inserted_stat[self._id][0]["end"]))
                return
            _LOGGER.debug("New starting datetime: %s", start)

            # Extra check to not strain the API too much:
            # If the last insert date is less than 24h away, simply exit here,
            # because we will not get any data from the API
            min_wait = timedelta(hours=24)
            delta_t = datetime.now(timezone.utc).replace(microsecond=0) - start.replace(microsecond=0)
            if delta_t <= min_wait:
                _LOGGER.debug(
                    "Not querying the API, because last update is not older than 24 hours. Earliest update in %s" % (min_wait - delta_t))
                return

        else:
            _LOGGER.error(f"unexpected result of get_last_statistics: {last_inserted_stat}")
            return

        try:
            smartmeter = Smartmeter(self.username, self.password)
            await self.hass.async_add_executor_job(smartmeter.login)
            zaehlpunkt = await self.get_zaehlpunkt(smartmeter)
            self._attr_extra_state_attributes = zaehlpunkt

            if not self.is_active(zaehlpunkt):
                self._available = False
                _LOGGER.debug("Smartmeter %s is not active" % zaehlpunkt)
                return
            else:
                self._available = True

            # Collect hourly data
            if init_meter:
                _LOGGER.warning("Starting import of historical data. This might take some time.")
                await self._import_historical_data(smartmeter)
            else:
                await self._import_statistics(smartmeter, start, _sum)

            self._updatets = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        except TimeoutError as e:
            self._available = False
            _LOGGER.warning("Error retrieving data from smart meter api - Timeout: %s" % e)
        except RuntimeError as e:
            self._available = False
            _LOGGER.exception("Error retrieving data from smart meter api - Error: %s" % e)

    async def _import_historical_data(self, smartmeter: Smartmeter):
        """Initialize the statistics by fetching three years of data"""
        recording = await self.get_historic_data(smartmeter)

        factor = 1.0
        if recording['unitOfMeasurement'] == 'WH':
            factor = 1e-3
        else:
            raise NotImplementedError(f'Unit {recording["unitOfMeasurement"]}" is not yet implemented. Please report!')

        dates = defaultdict(Decimal)

        for value in recording['values']:
            reading = Decimal(value['messwert'] * factor)
            ts = dt_util.parse_datetime(value['zeitVon'])
            ts_to = dt_util.parse_datetime(value['zeitBis'])
            qual = value['qualitaet']
            if qual != 'VAL':
                _LOGGER.warning(f"Historic data with different quality than 'VAL' detected: {value}")
            if ts.minute % 15 != 0 or ts.second != 0 or ts.microsecond != 0:
                _LOGGER.warning(f"Unexpected time detected in historic data: {value}")
            if (ts_to - ts) != timedelta(minutes=15):
                _LOGGER.warning(f"Unexpected time step detected in historic data: {value}")
            dates[ts.replace(minute=0)] += reading

        statistics = []
        metadata = StatisticMetaData(
            source="recorder",
            statistic_id=self._id,
            name=self.name,
            unit_of_measurement=self._attr_unit_of_measurement,
            has_mean=False,
            has_sum=True,
        )
        _LOGGER.debug(metadata)

        total_usage = Decimal(0)
        for ts, usage in sorted(dates.items(), key=itemgetter(0)):
            total_usage += usage
            statistics.append(StatisticData(start=ts, sum=total_usage, state=usage))

        _LOGGER.debug(f"Importing statistics from {statistics[0]} to {statistics[-1]}")
        async_import_statistics(self.hass, metadata, statistics)

    async def _import_statistics(self, smartmeter: Smartmeter, start: datetime, total_usage: Decimal):
        """Import hourly consumption data into the statistics module, using start date and sum"""
        # Have to be sure that the start datetime is aware of timezone, because we need to compare
        # it to other timezone aware datetimes in this function
        if start.tzinfo is None:
            raise ValueError("start datetime must be timezone-aware!")
        # Have to be sure that full minutes are used. otherwise, the API returns a different
        # interval
        start = start.replace(minute=0, second=0, microsecond=0)

        statistics = []
        metadata = StatisticMetaData(
            source="recorder",
            statistic_id=self._id,
            name=self.name,
            unit_of_measurement=self._attr_unit_of_measurement,
            has_mean=False,
            has_sum=True,
        )
        _LOGGER.debug(metadata)

        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        _LOGGER.debug("Selecting data up to %s" % now)
        while start < now:
            _LOGGER.debug("Select 24h of Data, using sum=%.3f, start=%s" % total_usage, start)
            consumption = await self.get_consumption(smartmeter, start)
            _LOGGER.debug(consumption)
            last_ts = start
            start += timedelta(hours=24)  # Next batch. Setting this here should avoid endless loops

            if 'values' not in consumption:
                _LOGGER.error(f"No values in API response! This likely indicates an API error. Original response: {consumption}")
                return

            # Check if this batch of data is valid and contains hourly statistics:
            if not consumption.get('optIn'):
                # TODO: actually, we could insert zero-usage data here, to increase the start time
                # for the next run. Otherwise, the same data is queried over and over.
                _LOGGER.warning(f"Data starting at {start} does not contain granular data! Opt-in was not set back then.")
                continue

            # Can actually check, if the whole batch can be skipped.
            if consumption.get('consumptionMinimum') == 0 and consumption.get('consumptionMaximum') == 0:
                _LOGGER.debug("Batch of data does not contain any consumption, skipping")
                continue

            for v in consumption['values']:
                # Timestamp has to be aware of timezone, parse_datetime does that.
                ts = dt_util.parse_datetime(v['timestamp'])
                if ts.minute != 0:
                    # This usually happens if the start date minutes are != 0
                    # However, we set them to 0 in this function, thus if this happens, the API has
                    # a problem...
                    _LOGGER.error("Minute of timestamp is non-zero, this must not happen!")
                    return
                if ts < last_ts:
                    # This should prevent any issues with ambiguous values though...
                    _LOGGER.warning(f"Timestamp from API ({ts}) is less than previously collected timestamp ({last_ts}), ignoring value!")
                    continue
                last_ts = ts
                if v['value'] is None:
                    # Usually this means that the measurement is not yet in the WSTW database.
                    # But could also be an error? Dunno...
                    # For now, we ignore these values, possibly that means we loose hours if these
                    # values come back later.
                    # However, it is not trivial (or even impossible?) to insert statistic values
                    # in between existing values, thus we can not do much.
                    continue
                usage = Decimal(v['value'] / 1000.0)  # Convert to kWh ...
                total_usage += usage  # ... and accumulate
                if v['isEstimated']:
                    # Can we do anything special here?
                    _LOGGER.debug("Estimated Value found for {ts}: {usage}")

                statistics.append(StatisticData(start=ts, sum=total_usage, state=usage))

        _LOGGER.debug(statistics)

        # Import the statistics data
        async_import_statistics(self.hass, metadata, statistics)
