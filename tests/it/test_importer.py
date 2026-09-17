"""Tests for Importer's daily/quarter-hour fallback and daily-floor overlay (issue #361)."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from it import bewegungsdaten_response
from wnsm.api.constants import ValueType
from wnsm.const import ATTRS_BEWEGUNGSDATEN
from wnsm.importer import Importer, _bucket_by_hour, _unit_factor
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


def _data(unit: str | None, values: list | None = None) -> dict:
    """Minimal translated bewegungsdaten shape, for tests that only care about unit/values."""
    return {"unitOfMeasurement": unit, "values": values or []}


def _value(ts: datetime, wert: float | None) -> dict:
    return {"zeitpunktVon": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "wert": wert, "geschaetzt": False}


def _importer(granularity: ValueType = ValueType.QUARTER_HOUR) -> Importer:
    return Importer(
        hass=None,
        async_smartmeter=AsyncMock(),
        zaehlpunkt=ZAEHLPUNKT,
        unit_of_measurement="kWh",
        granularity=granularity,
    )


def test_unit_factor_known_units():
    assert _unit_factor("WH") == 1e-3
    assert _unit_factor("KWH") == 1.0


def test_unit_factor_unknown_unit_raises():
    with pytest.raises(NotImplementedError):
        _unit_factor("MWH")


def test_bucket_by_hour_sums_same_hour_and_skips_none():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    values = [
        _value(datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc), 1.0),
        _value(datetime(2024, 1, 1, 10, 15, tzinfo=timezone.utc), 2.0),
        _value(datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc), None),
    ]

    dates = _bucket_by_hour(values, 1.0, start)

    assert dates == {datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc): Decimal("3.0")}


def test_bucket_by_hour_skips_out_of_order_timestamps():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    values = [
        _value(datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc), 5.0),
        _value(datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc), 99.0),  # before last_ts, ignored
    ]

    dates = _bucket_by_hour(values, 1.0, start)

    assert dates == {datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc): Decimal("5.0")}


@pytest.mark.asyncio
async def test_get_bewegungsdaten_returns_quarter_hour_data_without_fallback_when_available():
    importer = _importer(ValueType.QUARTER_HOUR)
    quarter_hour_data = _translated_response(ValueType.QUARTER_HOUR)
    importer.async_smartmeter.get_bewegungsdaten.return_value = quarter_hour_data

    result = await importer._get_bewegungsdaten(START, END)

    assert result == quarter_hour_data
    importer.async_smartmeter.get_bewegungsdaten.assert_awaited_once_with(
        ZAEHLPUNKT, START, END, ValueType.QUARTER_HOUR
    )


@pytest.mark.asyncio
async def test_get_bewegungsdaten_falls_back_to_daily_when_quarter_hour_unit_of_measurement_is_none():
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
async def test_get_bewegungsdaten_does_not_fall_back_when_only_values_are_empty_but_unit_is_present():
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
async def test_get_bewegungsdaten_does_not_retry_when_already_querying_daily_granularity():
    importer = _importer(ValueType.DAY)
    empty_daily = _translated_response(ValueType.DAY, no_descriptor=True)
    importer.async_smartmeter.get_bewegungsdaten.return_value = empty_daily

    result = await importer._get_bewegungsdaten(START, END)

    assert result == empty_daily
    importer.async_smartmeter.get_bewegungsdaten.assert_awaited_once_with(
        ZAEHLPUNKT, START, END, ValueType.DAY
    )


@pytest.mark.asyncio
async def test_collect_with_daily_floor_layers_quarter_hour_over_daily():
    importer = _importer(ValueType.QUARTER_HOUR)
    daily_reading = _value(START, 4.0)
    # quarter-hour is silent on START (no opt-in yet) but reports the next hour.
    qh_reading = _value(datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc), 9.0)
    importer.async_smartmeter.get_bewegungsdaten.side_effect = [
        _data("KWH", [daily_reading]), _data("KWH", [qh_reading]),
    ]

    dates = await importer._collect_with_daily_floor(START, END)

    assert dates == {START: Decimal("4.0"), datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc): Decimal("9.0")}
    importer.async_smartmeter.get_bewegungsdaten.assert_any_await(ZAEHLPUNKT, START, END, ValueType.DAY)
    importer.async_smartmeter.get_bewegungsdaten.assert_any_await(ZAEHLPUNKT, START, END, ValueType.QUARTER_HOUR)


@pytest.mark.asyncio
async def test_collect_with_daily_floor_quarter_hour_overrides_matching_hour():
    importer = _importer(ValueType.QUARTER_HOUR)
    daily_reading = _value(START, 4.0)
    qh_reading = _value(START, 9.0)  # same hour as the daily reading: quarter-hour wins
    importer.async_smartmeter.get_bewegungsdaten.side_effect = [
        _data("KWH", [daily_reading]), _data("KWH", [qh_reading]),
    ]

    dates = await importer._collect_with_daily_floor(START, END)

    assert dates == {START: Decimal("9.0")}


@pytest.mark.asyncio
async def test_collect_with_daily_floor_keeps_daily_when_quarter_hour_totally_empty():
    importer = _importer(ValueType.QUARTER_HOUR)
    daily_reading = _value(START, 4.0)
    importer.async_smartmeter.get_bewegungsdaten.side_effect = [_data("KWH", [daily_reading]), _data(None)]

    dates = await importer._collect_with_daily_floor(START, END)

    assert dates == {START: Decimal("4.0")}


@pytest.mark.asyncio
async def test_collect_with_daily_floor_returns_empty_when_daily_itself_is_empty():
    importer = _importer(ValueType.QUARTER_HOUR)
    importer.async_smartmeter.get_bewegungsdaten.return_value = _data(None)

    dates = await importer._collect_with_daily_floor(START, END)

    assert dates == {}
    importer.async_smartmeter.get_bewegungsdaten.assert_awaited_once()  # never even tries quarter-hour


@pytest.mark.asyncio
async def test_collect_dates_uses_daily_floor_only_for_initial_import():
    importer = _importer(ValueType.QUARTER_HOUR)
    daily_reading = _value(START, 4.0)
    qh_reading = _value(START, 9.0)
    importer.async_smartmeter.get_bewegungsdaten.side_effect = [
        _data("KWH", [daily_reading]), _data("KWH", [qh_reading]),
    ]

    dates = await importer._collect_dates(START, END, recover_quarter_hour=True)

    assert dates == {START: Decimal("9.0")}


@pytest.mark.asyncio
async def test_collect_dates_skips_daily_floor_for_incremental_import():
    importer = _importer(ValueType.QUARTER_HOUR)
    qh_reading = _value(START, 4.0)
    importer.async_smartmeter.get_bewegungsdaten.return_value = _data("KWH", [qh_reading])

    dates = await importer._collect_dates(START, END, recover_quarter_hour=False)

    assert dates == {START: Decimal("4.0")}
    importer.async_smartmeter.get_bewegungsdaten.assert_awaited_once()  # no daily floor fetched
