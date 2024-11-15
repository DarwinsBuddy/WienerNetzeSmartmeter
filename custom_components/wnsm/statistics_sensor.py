import logging
from collections import defaultdict
from datetime import timedelta, timezone, datetime
from decimal import Decimal
from operator import itemgetter

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_import_statistics, get_last_statistics,
)
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.util import dt as dt_util

from .api import Smartmeter
from .base_sensor import BaseSensor

_LOGGER = logging.getLogger(__name__)


class StatisticsSensor(BaseSensor, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

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

    def is_last_inserted_stat_valid(self, last_inserted_stat):
        return len(last_inserted_stat) == 1 and len(last_inserted_stat[self._id]) == 1 and \
            "sum" in last_inserted_stat[self._id][0] and "end" in last_inserted_stat[self._id][0]

    def prepare_start_off_point(self, last_inserted_stat):
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
            return None
        _LOGGER.debug("New starting datetime: %s", start)

        # Extra check to not strain the API too much:
        # If the last insert date is less than 24h away, simply exit here,
        # because we will not get any data from the API
        min_wait = timedelta(hours=24)
        delta_t = datetime.now(timezone.utc).replace(microsecond=0) - start.replace(microsecond=0)
        if delta_t <= min_wait:
            _LOGGER.debug(
                "Not querying the API, because last update is not older than 24 hours. Earliest update in %s" % (
                        min_wait - delta_t))
            return None
        return start, _sum

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

            if not self.is_last_inserted_stat_valid(last_inserted_stat):
                # No previous data - start from scratch
                _LOGGER.warning("Starting import of historical data. This might take some time.")
                await self._import_bewegungsdaten(smartmeter)
            else:
                start_off_point = self.prepare_start_off_point(last_inserted_stat)
                if start_off_point is None:
                    return
                start, _sum = start_off_point
                await self._import_statistics(smartmeter, start, _sum)

            # XXX: Note that the state of this sensor must never be an integer value, such as 0!
            # If it is set to any number, home assistant will assume that a negative consumption
            # compensated the last statistics entry and add a negative consumption in the energy
            # dashboard.
            # This is a technical debt of HA, as we cannot import statistics and have states at the
            # same time.
            # Due to None, the sensor will always show "unkown" - but that is currently the only way
            # how historical data can be imported without rewriting the database on our own...
            self._state = None
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
        _LOGGER.debug(f"Mapped historical data: {recording}")
        factor = 1.0
        if recording['unitOfMeasurement'] == 'WH':
            factor = 1e-3
        else:
            raise NotImplementedError(f'Unit {recording["unitOfMeasurement"]}" is not yet implemented. Please report!')

        dates = defaultdict(Decimal)
        if 'values' not in recording:
            raise ValueError("WienerNetze does not report historical data (yet)")
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
        if len(statistics) > 0:
            _LOGGER.debug(f"Importing statistics from {statistics[0]} to {statistics[-1]}")
        async_import_statistics(self.hass, metadata, statistics)

    async def _import_bewegungsdaten(self, smartmeter: Smartmeter):
        """Initialize the statistics by fetching three years of data"""
        recording = await self.get_bewegungsdaten(smartmeter)
        _LOGGER.debug(f"Mapped historical data: {recording}")
        if recording['unitOfMeasurement'] == 'WH':
            factor = 1e-3
        elif recording['unitOfMeasurement'] == 'KWH':
            factor = 1.0
        else:
            raise NotImplementedError(f'Unit {recording["unitOfMeasurement"]}" is not yet implemented. Please report!')

        dates = defaultdict(Decimal)
        if 'values' not in recording:
            raise ValueError("WienerNetze does not report historical data (yet)")
        for value in recording['values']:
            reading = Decimal(value['wert'] * factor)
            ts = dt_util.parse_datetime(value['zeitpunktVon'])
            ts_to = dt_util.parse_datetime(value['zeitpunktBis'])
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
            statistics.append(StatisticData(start=ts, sum=total_usage, state=float(usage)))
        if len(statistics) > 0:
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
            _LOGGER.debug(f"Select 24h of Data, using sum={total_usage:.3f}, start={start}")
            bewegungsdaten = await self.get_bewegungsdaten(smartmeter, start)
            _LOGGER.debug(bewegungsdaten)
            last_ts = start
            start += timedelta(hours=24)  # Next batch. Setting this here should avoid endless loops

            if 'values' not in bewegungsdaten:
                # before, this indicated an error. Since 2023-12-15 no more values means that
                # data is not available (yet) - but could still indicate an error...
                _LOGGER.debug(
                    f"No more values in API response. Possibly the end of the available data is reached. Original response: {bewegungsdaten}")
                # We break the loop here and hope that in the next iteration, data will be collected
                # again...
                # TODO: has to be carefully checked if the API can return a response without values
                # between responses WITH values! Otherwise, we produce here an endless wait for that
                # values to turn up.
                break

            total_consumption = sum([ v.get("wert", 0) for v in bewegungsdaten['values']])
            # Can actually check, if the whole batch can be skipped.
            if total_consumption == 0:
                _LOGGER.debug(f"Batch of data starting at {start} does not contain any consumption, skipping")
                continue

            for v in bewegungsdaten['values']:
                # Timestamp has to be aware of timezone, parse_datetime does that.
                ts = dt_util.parse_datetime(v['zeitpunktVon'])
                if ts < last_ts:
                    # This should prevent any issues with ambiguous values though...
                    _LOGGER.warning(
                        f"Timestamp from API ({ts}) is less than previously collected timestamp ({last_ts}), ignoring value!")
                    continue
                last_ts = ts
                if v['wert'] is None:
                    # Usually this means that the measurement is not yet in the WSTW database.
                    # But could also be an error? Dunno...
                    # For now, we ignore these values, possibly that means we loose hours if these
                    # values come back later.
                    # However, it is not trivial (or even impossible?) to insert statistic values
                    # in between existing values, thus we can not do much.
                    continue
                usage = Decimal(v['wert'])  # Convert to kWh ...
                total_usage += usage
                if v['geschaetzt']:
                    # Can we do anything special here?
                    _LOGGER.debug(f"Estimated Value found for {ts}: {usage}")

                statistics.append(StatisticData(start=ts, sum=total_usage, state=float(usage)))

        _LOGGER.debug(statistics)

        # Import the statistics data
        async_import_statistics(self.hass, metadata, statistics)
