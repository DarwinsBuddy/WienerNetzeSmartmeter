import logging
from datetime import datetime

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .AsyncSmartmeter import AsyncSmartmeter
from .api.constants import ValueType
from .const import DOMAIN
from .day_processing import extract_day_points
from .statistics_utils import as_utc, get_last_stats_timestamp

_LOGGER = logging.getLogger(__name__)


class DayStatisticsImporter:
    """Import DAY readings into long-term statistics with source timestamps."""

    def __init__(self, hass: HomeAssistant, async_smartmeter: AsyncSmartmeter, zaehlpunkt: str):
        self.hass = hass
        self.async_smartmeter = async_smartmeter
        self.zaehlpunkt = zaehlpunkt
        self.id = f"{DOMAIN}:{slugify(zaehlpunkt)}_day_v2"

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
            if last_start is None or ts > last_start:
                stats.append(StatisticData(start=ts, state=float(point.value_kwh), sum=None))

        if stats:
            _LOGGER.debug("Importing %s DAY statistics for %s", len(stats), self.zaehlpunkt)
            async_add_external_statistics(self.hass, self.get_statistics_metadata(), stats)
