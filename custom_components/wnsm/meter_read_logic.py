"""Shared METER_READ retrieval helpers for sensor entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .AsyncSmartmeter import AsyncSmartmeter
from .measurement_attributes import set_messwert_attributes
from .utils import build_reading_date_attributes


async def async_get_latest_meter_read_payload(
    async_smartmeter: AsyncSmartmeter,
    zaehlpunkt: str,
    zaehlpunkt_response: dict[str, Any],
) -> tuple[int | float | None, dict[str, Any]]:
    """Return latest meter read value and normalized attributes for a Zählpunkt."""
    reading_dates, attributes = build_reading_date_attributes(zaehlpunkt_response)
    meter_reads: list[int | float | None] = []

    selected_value: int | float | None = None
    selected_reading_date = None

    for reading_date in reading_dates:
        meter_reading = await async_smartmeter.get_meter_reading_from_historic_data(
            zaehlpunkt, reading_date, datetime.now()
        )
        meter_reads.append(meter_reading)
        if selected_value is None and meter_reading is not None:
            selected_value = meter_reading
            selected_reading_date = reading_date

    set_messwert_attributes(attributes, meter_reads)

    if selected_reading_date is not None:
        attributes["reading_date"] = selected_reading_date.isoformat()
    return selected_value, attributes
