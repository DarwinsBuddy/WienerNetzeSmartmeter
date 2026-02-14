import logging
from typing import Any

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import DOMAIN
from .statistics_utils import as_utc, get_last_stats_timestamp

_LOGGER = logging.getLogger(__name__)


class MainDailySnapshotStatisticsImporter:
    """Import METER_READ snapshot points into long-term statistics with reading-date timestamps."""

    def __init__(self, hass: HomeAssistant, zaehlpunkt: str):
        self.hass = hass
        self.zaehlpunkt = zaehlpunkt
        self.id = f"{DOMAIN}:{slugify(zaehlpunkt)}_main_daily_snapshot_v2"

    def get_statistics_metadata(self) -> StatisticMetaData:
        return StatisticMetaData(
            source=DOMAIN,
            statistic_id=self.id,
            name=f"{self.zaehlpunkt} Main Daily Snapshot",
            unit_of_measurement="kWh",
            has_mean=True,
            has_sum=False,
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

        stats = []
        for reading_date, meter_reading in reversed(points):
            start = as_utc(dt_util.parse_datetime(reading_date))
            if start is None:
                _LOGGER.warning(
                    "Skipping main snapshot import for %s: invalid reading_date '%s'",
                    self.zaehlpunkt,
                    reading_date,
                )
                continue
            if last_start is not None and start <= last_start:
                continue
            stats.append(StatisticData(start=start, state=float(meter_reading), sum=None))

        if stats:
            metadata = self.get_statistics_metadata()
            async_add_external_statistics(self.hass, metadata, stats)
