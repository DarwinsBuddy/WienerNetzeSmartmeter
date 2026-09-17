"""Tests for Importer._get_bewegungsdaten's daily-granularity fallback (issue #361)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from it import bewegungsdaten_response
from wnsm.api.constants import ValueType
from wnsm.const import ATTRS_BEWEGUNGSDATEN
from wnsm.importer import Importer
from wnsm.utils import translate_dict

CUSTOMER_ID = "1234567890"
ZAEHLPUNKT = "AT0010000000000000001000011111111"
START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime(2024, 1, 2, tzinfo=timezone.utc)


def _translated_response(granularity: ValueType, values_count: int = 10, no_descriptor: bool = False) -> dict:
    """Build the translated dict shape that AsyncSmartmeter.get_bewegungsdaten() returns."""
    raw = bewegungsdaten_response(CUSTOMER_ID, ZAEHLPUNKT, granularity=granularity,
                                  values_count=values_count, no_descriptor=no_descriptor)
    return translate_dict(raw, ATTRS_BEWEGUNGSDATEN)


def _importer(granularity: ValueType = ValueType.QUARTER_HOUR) -> Importer:
    return Importer(
        hass=None,
        async_smartmeter=AsyncMock(),
        zaehlpunkt=ZAEHLPUNKT,
        unit_of_measurement="kWh",
        granularity=granularity,
    )


@pytest.mark.asyncio
async def test_returns_quarter_hour_data_without_fallback_when_available():
    importer = _importer(ValueType.QUARTER_HOUR)
    quarter_hour_data = _translated_response(ValueType.QUARTER_HOUR)
    importer.async_smartmeter.get_bewegungsdaten.return_value = quarter_hour_data

    result = await importer._get_bewegungsdaten(START, END)

    assert result == quarter_hour_data
    importer.async_smartmeter.get_bewegungsdaten.assert_awaited_once_with(
        ZAEHLPUNKT, START, END, ValueType.QUARTER_HOUR
    )


@pytest.mark.asyncio
async def test_falls_back_to_daily_when_quarter_hour_unit_of_measurement_is_none():
    importer = _importer(ValueType.QUARTER_HOUR)
    empty_quarter_hour = _translated_response(ValueType.QUARTER_HOUR, no_descriptor=True)
    daily_data = _translated_response(ValueType.DAY)
    importer.async_smartmeter.get_bewegungsdaten.side_effect = [empty_quarter_hour, daily_data]

    result = await importer._get_bewegungsdaten(START, END)

    assert result == daily_data
    assert importer.async_smartmeter.get_bewegungsdaten.await_count == 2
    importer.async_smartmeter.get_bewegungsdaten.assert_any_await(ZAEHLPUNKT, START, END, ValueType.QUARTER_HOUR)
    importer.async_smartmeter.get_bewegungsdaten.assert_any_await(ZAEHLPUNKT, START, END, ValueType.DAY)


@pytest.mark.asyncio
async def test_does_not_fall_back_when_only_values_are_empty_but_unit_is_present():
    # A quarter-hour meter with no newly-finalised readings yet is a normal,
    # expected state (e.g. mid-cycle incremental poll) and must not trigger
    # an extra daily-fallback request on every such poll.
    importer = _importer(ValueType.QUARTER_HOUR)
    no_new_readings_yet = _translated_response(ValueType.QUARTER_HOUR, values_count=0)
    importer.async_smartmeter.get_bewegungsdaten.return_value = no_new_readings_yet

    result = await importer._get_bewegungsdaten(START, END)

    assert result == no_new_readings_yet
    importer.async_smartmeter.get_bewegungsdaten.assert_awaited_once_with(
        ZAEHLPUNKT, START, END, ValueType.QUARTER_HOUR
    )


@pytest.mark.asyncio
async def test_does_not_retry_when_already_querying_daily_granularity():
    importer = _importer(ValueType.DAY)
    empty_daily = _translated_response(ValueType.DAY, no_descriptor=True)
    importer.async_smartmeter.get_bewegungsdaten.return_value = empty_daily

    result = await importer._get_bewegungsdaten(START, END)

    assert result == empty_daily
    importer.async_smartmeter.get_bewegungsdaten.assert_awaited_once_with(
        ZAEHLPUNKT, START, END, ValueType.DAY
    )
