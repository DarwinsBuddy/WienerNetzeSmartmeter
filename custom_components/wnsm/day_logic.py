"""Shared DAY retrieval helpers for DAY sensor entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .AsyncSmartmeter import AsyncSmartmeter
from .api.constants import ValueType
from .day_processing import DayValuePoint, latest_two_day_points
from .measurement_attributes import set_messwert_attributes
from .utils import before, build_reading_date_attributes, today


async def async_get_latest_day_payload(
    async_smartmeter: AsyncSmartmeter,
    zaehlpunkt: str,
    zaehlpunkt_response: dict[str, Any],
) -> tuple[DayValuePoint | None, list[DayValuePoint], dict[str, Any]]:
    """Return latest normalized DAY point, latest two points, and attributes."""
    start = before(today(), 1)
    end = today()

    _, attributes = build_reading_date_attributes(zaehlpunkt_response)
    messwerte = await async_smartmeter.get_historic_data(
        zaehlpunkt,
        start,
        end,
        ValueType.DAY,
    )

    latest_two_points = latest_two_day_points(messwerte)
    set_messwert_attributes(
        attributes,
        [point.value_kwh for point in latest_two_points],
    )
    attributes["reading_dates"] = [point.reading_date for point in latest_two_points]

    latest = latest_two_points[0] if latest_two_points else None
    if latest is not None:
        attributes["reading_date"] = latest.reading_date

    return latest, latest_two_points, attributes


def day_query_window() -> tuple[datetime, datetime]:
    """Return canonical DAY query window (yesterday -> today)."""
    return before(today(), 1), today()
