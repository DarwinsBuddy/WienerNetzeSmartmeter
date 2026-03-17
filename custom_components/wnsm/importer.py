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
    get_last_statistics, async_add_external_statistics, StatisticMeanType,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from homeassistant.util.unit_conversion import EnergyConverter

from .AsyncSmartmeter import AsyncSmartmeter
from .api.constants import ValueType
from .api.errors import SmartmeterError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

UNIT_FACTORS = {"WH": 1e-3, "KWH": 1.0}


def _unit_factor(unit: Optional[str]) -> float:
    if unit not in UNIT_FACTORS:
        raise NotImplementedError(f'Unit "{unit}" is not yet implemented. Please report!')
    return UNIT_FACTORS[unit]


def _bucket_by_hour(values: list, factor: float, start: datetime) -> dict:
    """Sum raw bewegungsdaten values into per-hour usage deltas."""
    dates = defaultdict(Decimal)
    last_ts = start
    for value in values:
        ts = dt_util.parse_datetime(value['zeitpunktVon'])
        if ts < last_ts:
            # This should prevent any issues with ambiguous values though...
            _LOGGER.warning(f"Timestamp from API ({ts}) is less than previously collected timestamp ({last_ts}), ignoring value!")
            continue
        last_ts = ts
        if value['wert'] is None:
            # Usually this means that the measurement is not yet in the WSTW database.
            continue
        reading = Decimal(value['wert'] * factor)
        if ts.minute % 15 != 0 or ts.second != 0 or ts.microsecond != 0:
            _LOGGER.warning(f"Unexpected time detected in historic data: {value}")
        dates[ts.replace(minute=0)] += reading
        if value['geschaetzt']:
            _LOGGER.debug(f"Not seen that before: Estimated Value found for {ts}: {reading}")
    return dict(dates)


def _bucket(bewegungsdaten: dict, start: datetime) -> dict:
    factor = _unit_factor(bewegungsdaten['unitOfMeasurement'])
    return _bucket_by_hour(bewegungsdaten.get('values') or [], factor, start)


class Importer:

    def __init__(
        self,
        hass: HomeAssistant,
        async_smartmeter: AsyncSmartmeter,
        zaehlpunkt: str,
        unit_of_measurement: str,
        granularity: ValueType = ValueType.QUARTER_HOUR,
        price_entity_id: Optional[str] = None,
    ):
        self.id = f'{DOMAIN}:{zaehlpunkt.lower()}'
        self.cost_id = f'{DOMAIN}:{zaehlpunkt.lower()}_cost'
        self.zaehlpunkt = zaehlpunkt
        self.granularity = granularity
        self.unit_of_measurement = unit_of_measurement
        self.hass = hass
        self.async_smartmeter = async_smartmeter
        self.price_entity_id = price_entity_id

    def is_last_inserted_stat_valid(self, last_inserted_stat, stat_id=None):
        if stat_id is None:
            stat_id = self.id
        return len(last_inserted_stat) == 1 and len(last_inserted_stat[stat_id]) == 1 and \
            "sum" in last_inserted_stat[stat_id][0] and "end" in last_inserted_stat[stat_id][0]

    def prepare_start_off_point(self, last_inserted_stat, stat_id=None):
        if stat_id is None:
            stat_id = self.id
        # Previous data found in the statistics table
        _sum = Decimal(last_inserted_stat[stat_id][0]["sum"])
        # The next start is the previous end
        # XXX: since HA core 2022.12, we get a datetime and not a str...
        # XXX: since HA core 2023.03, we get a float and not a datetime...
        start = last_inserted_stat[stat_id][0]["end"]
        if isinstance(start, (int, float)):
            start = dt_util.utc_from_timestamp(start)
        if isinstance(start, str):
            start = dt_util.parse_datetime(start)

        if not isinstance(start, datetime):
            _LOGGER.error("HA core decided to change the return type AGAIN! "
                          "Please open a bug report. "
                          "Additional Information: %s Type: %s",
                          last_inserted_stat,
                          type(last_inserted_stat[stat_id][0]["end"]))
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

    def _get_cost_unit(self) -> str:
        """
        Derive the cost unit from the price sensor's unit of measurement.
        If the price sensor reports e.g. 'EUR/kWh' or 'ct/kWh', the cost unit
        is the currency part (e.g. 'EUR' or 'ct'). If the unit doesn't contain
        a '/', it is used as-is.
        """
        if self.price_entity_id is None:
            return "EUR"
        state = self.hass.states.get(self.price_entity_id)
        if state is None:
            return "EUR"
        unit = state.attributes.get("unit_of_measurement", "EUR")
        if "/" in unit:
            return unit.split("/")[0].strip()
        return unit

    def get_statistics_metadata(self):
        return StatisticMetaData(
            source=DOMAIN,
            statistic_id=self.id,
            name=self.zaehlpunkt,
            unit_of_measurement=self.unit_of_measurement,
            mean_type=StatisticMeanType.NONE,
            unit_class=EnergyConverter.UNIT_CLASS,
            has_sum=True,
        )

    def get_cost_statistics_metadata(self) -> StatisticMetaData:
        """Return StatisticMetaData for the energy cost statistic."""
        cost_unit = self._get_cost_unit()
        return StatisticMetaData(
            source=DOMAIN,
            statistic_id=self.cost_id,
            name=f"{self.zaehlpunkt} Cost",
            unit_of_measurement=cost_unit,
            mean_type=StatisticMeanType.NONE,
            unit_class=None,
            has_sum=True,
        )

    async def _get_price_statistics(self, start: datetime, end: datetime) -> dict:
        """
        Query HA long-term statistics for the price sensor over [start, end].
        Returns a dict mapping hourly timestamps (datetime, UTC) -> mean price (float).
        Only hours where a mean value exists are included.
        """
        if self.price_entity_id is None:
            return {}

        try:
            price_stats = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period,
                self.hass,
                start,
                end,
                {self.price_entity_id},
                "hour",
                None,      # units — use native units
                {"mean"},  # we only need mean
            )
        except Exception as e:
            _LOGGER.warning("Failed to query price statistics for %s: %s", self.price_entity_id, e)
            return {}

        if self.price_entity_id not in price_stats:
            _LOGGER.debug(
                "No statistics found for price sensor %s in range %s - %s",
                self.price_entity_id, start, end
            )
            return {}

        result = {}
        for entry in price_stats[self.price_entity_id]:
            mean = entry.get("mean")
            if mean is None:
                continue
            ts = entry.get("start")
            if ts is None:
                continue
            # Normalise to UTC datetime with no sub-hour precision
            if isinstance(ts, (int, float)):
                ts = dt_util.utc_from_timestamp(ts)
            if isinstance(ts, str):
                ts = dt_util.parse_datetime(ts)
            if not isinstance(ts, datetime):
                continue
            ts = ts.replace(minute=0, second=0, microsecond=0)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            result[ts] = float(mean)

        _LOGGER.debug(
            "Retrieved %d hourly price entries for %s", len(result), self.price_entity_id
        )
        return result

    async def async_import(self):
        # Query the statistics database for the last energy value
        last_inserted_stat = await get_instance(
            self.hass
        ).async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,  # Get at most one entry
            self.id,  # of this sensor
            True,  # convert the units
            # XXX: since HA core 2022.12 need to specify this:
            {"sum", "state"},  # the fields we want to query
        )
        _LOGGER.debug("Last inserted stat: %s" % last_inserted_stat)

        # Query the statistics database for the last cost value (if price sensor configured)
        last_inserted_cost_stat = {}
        if self.price_entity_id:
            last_inserted_cost_stat = await get_instance(
                self.hass
            ).async_add_executor_job(
                get_last_statistics,
                self.hass,
                1,
                self.cost_id,
                True,
                {"sum", "state"},
            )
            _LOGGER.debug("Last inserted cost stat: %s", last_inserted_cost_stat)

        try:
            await self.async_smartmeter.login()
            zaehlpunkt = await (self.async_smartmeter.get_zaehlpunkt(self.zaehlpunkt))

            if not self.async_smartmeter.is_active(zaehlpunkt):
                _LOGGER.debug("Smartmeter %s is not active" % zaehlpunkt)
                return

            energy_throttled = False
            if not self.is_last_inserted_stat_valid(last_inserted_stat):
                # No previous energy data - start from scratch
                _LOGGER.warning("Starting import of historical data. This might take some time.")
                _sum = await self._initial_import_statistics()
            else:
                start_off_point = self.prepare_start_off_point(last_inserted_stat)
                if start_off_point is None:
                    energy_throttled = True
                else:
                    start, _sum = start_off_point
                    _sum = await self._incremental_import_statistics(start, _sum)

            # Determine cost starting point independently of energy starting point.
            # The cost import is not throttled by the energy 24h check — when the
            # price sensor is first configured there will be no cost stats yet and
            # we need to do the full historical import regardless.
            if self.price_entity_id:
                if not self.is_last_inserted_cost_stat_valid(last_inserted_cost_stat):
                    _LOGGER.info(
                        "Starting full cost statistic import for %s using price sensor %s",
                        self.zaehlpunkt, self.price_entity_id
                    )
                    await self._initial_import_cost_statistics()
                else:
                    cost_start_off_point = self.prepare_start_off_point(
                        last_inserted_cost_stat, stat_id=self.cost_id
                    )
                    if cost_start_off_point is not None:
                        cost_start, cost_sum = cost_start_off_point
                        await self._incremental_import_cost_statistics(cost_start, cost_sum)

            # XXX: Note that the state of this sensor must never be an integer value, such as 0!
            # If it is set to any number, home assistant will assume that a negative consumption
            # compensated the last statistics entry and add a negative consumption in the energy
            # dashboard.
            # This is a technical debt of HA, as we cannot import statistics and have states at the
            # same time.
            # Due to None, the sensor will always show "unkown" - but that is currently the only way
            # how historical data can be imported without rewriting the database on our own...
            last_inserted_stat = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics,
                self.hass,
                1,  # Get at most one entry
                self.id,  # of this sensor's statistics
                True,  # convert the units
                {"sum"}  # the fields we want to query
            )
            _LOGGER.debug("Last inserted stat: %s", last_inserted_stat)
        except TimeoutError as e:
            _LOGGER.warning("Error retrieving data from smart meter api - Timeout: %s" % e)
        except (RuntimeError, SmartmeterError) as e:
            error_response = getattr(e, "error_response", None)
            if error_response:
                _LOGGER.warning("Error retrieving data from smart meter api - Error: %s; Response: %s", e, error_response)
            else:
                _LOGGER.warning("Error retrieving data from smart meter api - Error: %s", e)

    def is_last_inserted_cost_stat_valid(self, last_inserted_cost_stat):
        """Check whether the cost statistic has valid prior data."""
        return (
            len(last_inserted_cost_stat) == 1
            and len(last_inserted_cost_stat.get(self.cost_id, [])) == 1
            and "sum" in last_inserted_cost_stat[self.cost_id][0]
            and "end" in last_inserted_cost_stat[self.cost_id][0]
        )

    async def _initial_import_statistics(self):
        # Only the initial backfill can span a granularity opt-in, so only it
        # layers quarter-hour data over a daily floor.
        return await self._import_statistics(recover_quarter_hour=True)

    async def _incremental_import_statistics(self, start: datetime, total_usage: Decimal):
        return await self._import_statistics(start=start, total_usage=total_usage)

    async def _fetch(self, start: datetime, end: datetime, granularity: ValueType) -> dict:
        return await self.async_smartmeter.get_bewegungsdaten(self.zaehlpunkt, start, end, granularity)

    async def _get_bewegungsdaten(self, start: datetime, end: datetime) -> dict:
        """Fetch at the configured granularity, falling back to daily once if empty."""
        data = await self._fetch(start, end, self.granularity)
        # WienerNetze often leaves the V002 quarter-hour feed empty (einheit: null)
        # even when the meter is opted into 15-min values; daily (V001) still works.
        if self.granularity != ValueType.DAY and data.get('unitOfMeasurement') is None:
            _LOGGER.info("No %s data for %s; falling back to daily granularity",
                         self.granularity.value, self.zaehlpunkt)
            return await self._fetch(start, end, ValueType.DAY)
        return data

    async def _collect_with_daily_floor(self, start: datetime, end: datetime) -> dict:
        """Fetch daily as a floor and layer quarter-hour on top, unconditionally.

        WienerNetze may report a valid quarter-hour response that silently omits
        everything before the real opt-in date, so we can't tell from the
        quarter-hour fetch alone whether the daily floor is needed - always fetch
        both and let quarter-hour win wherever it actually reports a value.
        """
        daily = await self._fetch(start, end, ValueType.DAY)
        if daily.get('unitOfMeasurement') is None:
            _LOGGER.warning("Unit of measurement is None! Aborting import...")
            return {}
        dates = _bucket(daily, start)

        quarter_hour = await self._fetch(start, end, ValueType.QUARTER_HOUR)
        if quarter_hour.get('unitOfMeasurement') is None:
            return dates
        return {**dates, **_bucket(quarter_hour, start)}

    async def _collect_dates(self, start: datetime, end: datetime, recover_quarter_hour: bool) -> dict:
        if recover_quarter_hour and self.granularity == ValueType.QUARTER_HOUR:
            return await self._collect_with_daily_floor(start, end)

        bewegungsdaten = await self._get_bewegungsdaten(start, end)
        _LOGGER.debug(f"Mapped historical data: {bewegungsdaten}")
        if bewegungsdaten['unitOfMeasurement'] is None:
            _LOGGER.warning("Unit of measurement is None! Aborting import...")
            return {}
        return _bucket(bewegungsdaten, start)

    async def _initial_import_cost_statistics(self):
        """Import cost statistics from the beginning of available price history."""
        start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=365 * 3)
        return await self._import_cost_statistics(start=start, total_cost=Decimal(0))

    async def _incremental_import_cost_statistics(self, start: datetime, total_cost: Decimal):
        return await self._import_cost_statistics(start=start, total_cost=total_cost)

    async def _import_statistics(self, start: datetime = None, end: datetime = None, total_usage: Decimal = Decimal(0),
                                 recover_quarter_hour: bool = False) -> Optional[Decimal]:
        """Import energy statistics"""

        start = start if start is not None else datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=365 * 3)
        end = end if end is not None else datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        if start.tzinfo is None:
            raise ValueError("start datetime must be timezone-aware!")

        _LOGGER.debug("Selecting data up to %s" % end)
        if start > end:
            _LOGGER.warning(f"Ignoring async update since last import happened in the future (should not happen) {start} > {end}")
            return None

        dates = await self._collect_dates(start, end, recover_quarter_hour)
        if not dates or sum(dates.values()) == 0:
            _LOGGER.debug(f"Batch of data starting at {start} does not contain any bewegungsdaten. Seems there is nothing to import, yet.")
            return None

        statistics = []
        metadata = self.get_statistics_metadata()
        for ts, usage in sorted(dates.items(), key=itemgetter(0)):
            total_usage += usage
            statistics.append(StatisticData(start=ts, sum=total_usage, state=float(usage)))
        _LOGGER.debug(f"Importing statistics from {statistics[0]} to {statistics[-1]}")
        async_add_external_statistics(self.hass, metadata, statistics)
        return total_usage

    async def _import_cost_statistics(
        self,
        start: datetime,
        end: datetime = None,
        total_cost: Decimal = Decimal(0),
    ):
        """
        Compute and import cost statistics by multiplying hourly energy usage
        (from HA long-term statistics) by the hourly price (from the price sensor's
        long-term statistics). Only hours where both datasets have data are included.
        """
        if self.price_entity_id is None:
            return total_cost

        end = end if end is not None else datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        if start.tzinfo is None:
            raise ValueError("start datetime must be timezone-aware!")

        if start > end:
            _LOGGER.debug("Cost import skipped: start (%s) > end (%s)", start, end)
            return total_cost

        _LOGGER.debug("Importing cost statistics from %s to %s", start, end)

        # Fetch hourly price data from HA statistics
        prices = await self._get_price_statistics(start, end)
        if not prices:
            _LOGGER.debug(
                "No price data available for %s in range %s - %s, skipping cost import",
                self.price_entity_id, start, end
            )
            return total_cost

        # Fetch hourly energy data from HA statistics (already imported energy stats)
        try:
            energy_stats = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period,
                self.hass,
                start,
                end,
                {self.id},
                "hour",
                None,
                {"state"},
            )
        except Exception as e:
            _LOGGER.warning("Failed to query energy statistics for cost calculation: %s", e)
            return total_cost

        if self.id not in energy_stats or not energy_stats[self.id]:
            _LOGGER.debug("No energy statistics found for %s in range %s - %s", self.id, start, end)
            return total_cost

        # Build a timestamp -> hourly_usage lookup from energy stats
        energy_by_hour = {}
        for entry in energy_stats[self.id]:
            state_val = entry.get("state")
            if state_val is None:
                continue
            ts = entry.get("start")
            if ts is None:
                continue
            if isinstance(ts, (int, float)):
                ts = dt_util.utc_from_timestamp(ts)
            if isinstance(ts, str):
                ts = dt_util.parse_datetime(ts)
            if not isinstance(ts, datetime):
                continue
            ts = ts.replace(minute=0, second=0, microsecond=0)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            energy_by_hour[ts] = Decimal(str(state_val))

        if not energy_by_hour:
            _LOGGER.debug("No usable energy data found for cost calculation in range %s - %s", start, end)
            return total_cost

        # Compute cost for each hour where both energy and price are available
        cost_statistics = []
        cost_metadata = self.get_cost_statistics_metadata()
        skipped = 0

        for ts in sorted(energy_by_hour.keys()):
            usage_kwh = energy_by_hour[ts]
            price = prices.get(ts)
            if price is None:
                skipped += 1
                continue
            hourly_cost = usage_kwh * Decimal(str(price))
            total_cost += hourly_cost
            cost_statistics.append(
                StatisticData(start=ts, sum=total_cost, state=float(hourly_cost))
            )

        if skipped > 0:
            _LOGGER.debug(
                "Skipped %d hours without matching price data for %s",
                skipped, self.price_entity_id
            )

        if cost_statistics:
            _LOGGER.debug(
                "Importing %d cost statistic entries from %s to %s",
                len(cost_statistics),
                cost_statistics[0],
                cost_statistics[-1],
            )
            async_add_external_statistics(self.hass, cost_metadata, cost_statistics)
        else:
            _LOGGER.debug("No overlapping energy+price data found, no cost statistics written")

        return total_cost
