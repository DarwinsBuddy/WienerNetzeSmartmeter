import logging
from collections import defaultdict
from datetime import timedelta, timezone, datetime
from decimal import Decimal
from operator import itemgetter
from typing import Optional

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData
)
from homeassistant.components.recorder.statistics import (
    get_last_statistics, async_add_external_statistics, StatisticMeanType
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from homeassistant.util.unit_conversion import EnergyConverter

from .AsyncSmartmeter import AsyncSmartmeter
from .api.constants import ValueType
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class Importer:

    def __init__(self, hass: HomeAssistant, async_smartmeter: AsyncSmartmeter, zaehlpunkt: str, unit_of_measurement: str, granularity: ValueType = ValueType.QUARTER_HOUR, statistic_id: str | None = None, statistic_name: str | None = None, customer_id: str | None = None, profile_role: str | None = None):
        self.id = statistic_id or f'{DOMAIN}:{zaehlpunkt.lower()}'
        self.zaehlpunkt = zaehlpunkt
        self.granularity = granularity
        self.unit_of_measurement = unit_of_measurement
        self.hass = hass
        self.async_smartmeter = async_smartmeter
        self.statistic_name = statistic_name or zaehlpunkt
        self.customer_id = customer_id
        self.profile_role = profile_role

    def is_last_inserted_stat_valid(self, last_inserted_stat):
        return len(last_inserted_stat) == 1 and len(last_inserted_stat[self.id]) == 1 and            "sum" in last_inserted_stat[self.id][0] and "end" in last_inserted_stat[self.id][0]

    def prepare_start_off_point(self, last_inserted_stat):

        _sum = Decimal(last_inserted_stat[self.id][0]["sum"])



        start = last_inserted_stat[self.id][0]["end"]
        if isinstance(start, (int, float)):
            start = dt_util.utc_from_timestamp(start)
        if isinstance(start, str):
            start = dt_util.parse_datetime(start)

        if not isinstance(start, datetime):
            _LOGGER.error("HA core decided to change the return type AGAIN! "
                          "Please open a bug report. "
                          "Additional Information: %s Type: %s",
                          last_inserted_stat,
                          type(last_inserted_stat[self.id][0]["end"]))
            return None
        _LOGGER.debug("New starting datetime: %s", start)




        min_wait = timedelta(hours=24)
        delta_t = datetime.now(timezone.utc).replace(microsecond=0) - start.replace(microsecond=0)
        if delta_t <= min_wait:
            _LOGGER.debug(
                "Not querying the API, because last update is not older than 24 hours. Earliest update in %s" % (
                        min_wait - delta_t))
            return None
        return start, _sum

    async def async_import(self):


        last_inserted_stat = await get_instance(
            self.hass
        ).async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,
            self.id,
            True,

            {"sum", "state"},
        )
        _LOGGER.debug("Last inserted stat: %s" % last_inserted_stat)
        try:
            await self.async_smartmeter.login()
            zaehlpunkt = await (self.async_smartmeter.get_zaehlpunkt(self.zaehlpunkt))

            if not self.async_smartmeter.is_active(zaehlpunkt):
                _LOGGER.debug("Smartmeter %s is not active" % zaehlpunkt)
                return

            if self.profile_role is None:
                _LOGGER.warning("Skipping import for %s because no profile role was resolved.", self.id)
                return

            if not self.is_last_inserted_stat_valid(last_inserted_stat):

                _LOGGER.warning("Starting import of historical data. This might take some time.")
                _sum = await self._initial_import_statistics()
            else:
                start_off_point = self.prepare_start_off_point(last_inserted_stat)
                if start_off_point is None:
                    return
                start, _sum = start_off_point
                _sum = await self._incremental_import_statistics(start, _sum)









            last_inserted_stat = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics,
                self.hass,
                1,
                self.id,
                True,
                {"sum"}
            )
            _LOGGER.debug("Last inserted stat: %s", last_inserted_stat)
        except TimeoutError as e:
            _LOGGER.warning("Error retrieving data from smart meter api - Timeout: %s" % e)
        except Exception as e:
            _LOGGER.exception("Error retrieving data from smart meter api - Error: %s" % e)

    def get_statistics_metadata(self):
        return StatisticMetaData(
            source=DOMAIN,
            statistic_id=self.id,
            name=self.statistic_name,
            unit_of_measurement=self.unit_of_measurement,
            mean_type=StatisticMeanType.NONE,
            unit_class=EnergyConverter.UNIT_CLASS,
            has_sum=True,
        )

    async def async_get_last_sum(self) -> float | None:
        last_inserted_stat = await get_instance(
            self.hass
        ).async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,
            self.id,
            True,
            {"sum"},
        )
        if self.id in last_inserted_stat and len(last_inserted_stat[self.id]) > 0:
            return float(last_inserted_stat[self.id][0].get("sum"))
        return None

    async def _initial_import_statistics(self):
        return await self._import_statistics()

    async def _incremental_import_statistics(self, start: datetime, total_usage: Decimal):
        return await self._import_statistics(start=start, total_usage=total_usage)

    async def _import_statistics(self, start: datetime = None, end: datetime = None, total_usage: Decimal = Decimal(0)) -> Optional[Decimal]:


        start = start if start is not None else datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=365 * 3)
        end = end if end is not None else datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        if start.tzinfo is None:
            raise ValueError("start datetime must be timezone-aware!")

        _LOGGER.debug("Selecting data up to %s" % end)
        if start > end:
            _LOGGER.warning(f"Ignoring async update since last import happened in the future (should not happen) {start} > {end}")
            return None

        bewegungsdaten = await self.async_smartmeter.get_bewegungsdaten_by_profile_role(
            self.customer_id,
            self.zaehlpunkt,
            self.profile_role,
            start,
            end,
            "NONE",
        )
        _LOGGER.debug(f"Mapped historical data: {bewegungsdaten}")
        values = bewegungsdaten.get("values", [])
        if len(values) == 0:
            _LOGGER.debug(
                "No historical values returned for %s (role %s) in window %s - %s. Keeping existing statistics.",
                self.id,
                self.profile_role,
                start,
                end,
            )
            return total_usage

        if bewegungsdaten['unitOfMeasurement'] is None:
            _LOGGER.warning(
                "Unit of measurement is None for %s although %s values were returned. Skipping this import window.",
                self.id,
                len(values),
            )
            return total_usage
        elif bewegungsdaten['unitOfMeasurement'] == 'WH':
            factor = 1e-3
        elif bewegungsdaten['unitOfMeasurement'] == 'KWH':
            factor = 1.0
        else:
            raise NotImplementedError(f'Unit {bewegungsdaten["unitOfMeasurement"]}" is not yet implemented. Please report!')

        dates = defaultdict(Decimal)
        total_consumption = sum([v.get("wert", 0) for v in values])

        if total_consumption == 0:
            _LOGGER.debug(
                "Batch of data starting at %s for %s contains only zero values. Keeping existing statistics.",
                start,
                self.id,
            )
            return total_usage

        last_ts = start
        for value in values:
            ts = dt_util.parse_datetime(value['zeitpunktVon'])
            if ts < last_ts:

                _LOGGER.warning(f"Timestamp from API ({ts}) is less than previously collected timestamp ({last_ts}), ignoring value!")
                continue
            last_ts = ts
            if value['wert'] is None:

                continue
            reading = Decimal(value['wert'] * factor)
            if ts.minute % 15 != 0 or ts.second != 0 or ts.microsecond != 0:
                _LOGGER.warning(f"Unexpected time detected in historic data: {value}")
            dates[ts.replace(minute=0)] += reading
            if value['geschaetzt']:
                _LOGGER.debug(f"Not seen that before: Estimated Value found for {ts}: {reading}")

        statistics = []
        metadata = self.get_statistics_metadata()

        for ts, usage in sorted(dates.items(), key=itemgetter(0)):
            total_usage += usage
            statistics.append(StatisticData(start=ts, sum=total_usage, state=float(usage)))
        if len(statistics) > 0:
            _LOGGER.debug(f"Importing statistics from {statistics[0]} to {statistics[-1]}")
        async_add_external_statistics(self.hass, metadata, statistics)
        return total_usage
