"""Shared helpers for recorder statistics importers."""

from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import get_last_statistics
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


def as_utc(value: datetime | None) -> datetime | None:
    """Normalize datetime to timezone-aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_stats_timestamp(value: datetime | str | int | float | None) -> datetime | None:
    """Parse Home Assistant statistics timestamp variants."""
    if isinstance(value, (int, float)):
        value = dt_util.utc_from_timestamp(value)
    elif isinstance(value, str):
        value = dt_util.parse_datetime(value)
    if isinstance(value, datetime):
        return as_utc(value)
    return None


async def get_last_stats_timestamp(
    hass: HomeAssistant,
    statistic_id: str,
    field: str,
) -> datetime | None:
    """Read and parse last imported timestamp field for a statistic_id."""
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics,
        hass,
        1,
        statistic_id,
        True,
        {field},
    )
    if statistic_id in last and len(last[statistic_id]) == 1:
        return parse_stats_timestamp(last[statistic_id][0].get(field))
    return None
