import logging
from decimal import Decimal
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics, get_last_statistics
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import DOMAIN
from .statistics_utils import as_utc, get_last_stats_timestamp, parse_stats_timestamp

_LOGGER = logging.getLogger(__name__)


class MainDailySnapshotStatisticsImporter:
    """Import METER_READ snapshot points into long-term statistics with reading-date timestamps."""

    def __init__(self, hass: HomeAssistant, zaehlpunkt: str):
        self.hass = hass
        self.zaehlpunkt = zaehlpunkt
        self.id = f"{DOMAIN}:{slugify(zaehlpunkt)}_main_daily_snapshot_v2"
        self.sum_id = f"{DOMAIN}:{slugify(zaehlpunkt)}_main_daily_snapshot_sum_v1"

    def get_statistics_metadata(self) -> StatisticMetaData:
        return StatisticMetaData(
            source=DOMAIN,
            statistic_id=self.id,
            name=f"{self.zaehlpunkt} Main Daily Snapshot",
            unit_of_measurement="kWh",
            has_mean=True,
            has_sum=False,
        )

    def get_sum_statistics_metadata(self) -> StatisticMetaData:
        return StatisticMetaData(
            source=DOMAIN,
            statistic_id=self.sum_id,
            name=f"{self.zaehlpunkt} Main Daily Snapshot Sum",
            unit_of_measurement="kWh",
            has_mean=False,
            has_sum=True,
        )

    def _extract_points_from_attributes(
        self,
        payload_attributes: dict[str, Any],
    ) -> list[tuple[str, int | float]]:
        """Extract up to two snapshot points from payload attributes (newest first)."""
        reading_dates = payload_attributes.get("reading_dates", [])
        messwerte = [
            payload_attributes.get("messwert1"),
            payload_attributes.get("messwert2"),
        ]

        points: list[tuple[str, int | float]] = []
        for idx, value in enumerate(messwerte):
            if value is None or idx >= len(reading_dates):
                continue
            reading_date = reading_dates[idx]
            if isinstance(reading_date, str):
                points.append((reading_date, value))
        return points

    async def async_import_from_payload(self, payload_attributes: dict[str, Any]) -> None:
        """Import one or two snapshot points from payload attributes."""
        points = self._extract_points_from_attributes(payload_attributes)
        if not points:
            _LOGGER.debug("Skipping main snapshot import for %s: no valid points in payload", self.zaehlpunkt)
            return

        last_start = await get_last_stats_timestamp(self.hass, self.id, "start")

        last_sum = Decimal(0)
        last_sum_end = None
        last_sum_state = None
        last_sum_stat = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,
            self.sum_id,
            True,
            {"sum", "state", "end"},
        )
        if self.sum_id in last_sum_stat and len(last_sum_stat[self.sum_id]) == 1:
            row = last_sum_stat[self.sum_id][0]
            if row.get("sum") is not None:
                last_sum = Decimal(str(row.get("sum")))
            if row.get("state") is not None:
                last_sum_state = Decimal(str(row.get("state")))
            last_sum_end = parse_stats_timestamp(row.get("end"))

        state_stats = []
        sum_stats = []

        for reading_date, meter_reading in reversed(points):
            start = as_utc(dt_util.parse_datetime(reading_date))
            if start is None:
                _LOGGER.warning(
                    "Skipping main snapshot import for %s: invalid reading_date '%s'",
                    self.zaehlpunkt,
                    reading_date,
                )
                continue

            current_reading = Decimal(str(meter_reading))

            if last_start is None or start > last_start:
                state_stats.append(StatisticData(start=start, state=float(current_reading), sum=None))

            if last_sum_end is None or start > last_sum_end:
                usage = Decimal(0)
                if last_sum_state is not None:
                    usage = current_reading - last_sum_state
                    if usage < 0:
                        _LOGGER.warning(
                            "Detected decreasing snapshot meter read for %s (previous=%s, current=%s). Ignoring delta.",
                            self.zaehlpunkt,
                            last_sum_state,
                            current_reading,
                        )
                        usage = Decimal(0)
                last_sum += usage
                sum_stats.append(StatisticData(start=start, state=float(current_reading), sum=float(last_sum)))
                last_sum_state = current_reading

        if state_stats:
            async_add_external_statistics(self.hass, self.get_statistics_metadata(), state_stats)
        if sum_stats:
            async_add_external_statistics(self.hass, self.get_sum_statistics_metadata(), sum_stats)
