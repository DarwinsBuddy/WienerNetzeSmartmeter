import logging
from datetime import datetime
from decimal import Decimal

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .AsyncSmartmeter import AsyncSmartmeter
from .api.constants import ValueType
from .const import DOMAIN
from .day_processing import extract_day_points
from .statistics_utils import as_utc, get_last_stats_timestamp, parse_stats_timestamp

_LOGGER = logging.getLogger(__name__)


class DayStatisticsImporter:
    """Import DAY readings into long-term statistics with source timestamps."""

    def __init__(self, hass: HomeAssistant, async_smartmeter: AsyncSmartmeter, zaehlpunkt: str):
        self.hass = hass
        self.async_smartmeter = async_smartmeter
        self.zaehlpunkt = zaehlpunkt
        self.id = f"{DOMAIN}:{slugify(zaehlpunkt)}_day_v2"
        self.sum_id = f"{DOMAIN}:{slugify(zaehlpunkt)}_day_sum_v1"

    def get_statistics_metadata(self) -> StatisticMetaData:
        return StatisticMetaData(
            source=DOMAIN,
            statistic_id=self.id,
            name=f"{self.zaehlpunkt} Day",
            unit_of_measurement="kWh",
            has_mean=True,
            has_sum=False,
        )

    def get_sum_statistics_metadata(self) -> StatisticMetaData:
        return StatisticMetaData(
            source=DOMAIN,
            statistic_id=self.sum_id,
            name=f"{self.zaehlpunkt} Day Sum",
            unit_of_measurement="kWh",
            has_mean=False,
            has_sum=True,
        )

    async def async_import(self, date_from: datetime, date_to: datetime) -> None:
        """Import statistics newer than the latest imported sample."""
        last_start = await get_last_stats_timestamp(self.hass, self.id, "start")

        last_sum = Decimal(0)
        last_sum_end = None
        last_sum_stat = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,
            self.sum_id,
            True,
            {"sum", "end"},
        )
        if self.sum_id in last_sum_stat and len(last_sum_stat[self.sum_id]) == 1:
            row = last_sum_stat[self.sum_id][0]
            if row.get("sum") is not None:
                last_sum = Decimal(str(row.get("sum")))
            last_sum_end = parse_stats_timestamp(row.get("end"))

        raw = await self.async_smartmeter.get_historic_data(
            self.zaehlpunkt,
            date_from,
            date_to,
            ValueType.DAY,
        )
        points = extract_day_points(raw)

        state_stats = []
        sum_stats = []

        for point in sorted(points, key=lambda p: p.source_timestamp):
            ts = as_utc(point.source_timestamp)
            value = Decimal(str(point.value_kwh))

            if last_start is None or ts > last_start:
                state_stats.append(StatisticData(start=ts, state=float(value), sum=None))

            if last_sum_end is None or ts > last_sum_end:
                last_sum += value
                sum_stats.append(StatisticData(start=ts, state=float(value), sum=last_sum))

        if state_stats:
            _LOGGER.debug("Importing %s DAY statistics for %s", len(state_stats), self.zaehlpunkt)
            async_add_external_statistics(self.hass, self.get_statistics_metadata(), state_stats)

        if sum_stats:
            _LOGGER.debug("Importing %s DAY sum statistics for %s", len(sum_stats), self.zaehlpunkt)
            async_add_external_statistics(self.hass, self.get_sum_statistics_metadata(), sum_stats)
