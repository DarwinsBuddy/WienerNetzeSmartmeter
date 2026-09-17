"""Tests for Importer's daily/quarter-hour fallback and daily-floor overlay (issue #361)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.recorder.models import StatisticData

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


def test_bucket_by_hour_logs_unexpected_time_and_estimated_value(caplog):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    value = {"zeitpunktVon": "2024-01-01T10:05:00Z", "wert": 1.0, "geschaetzt": True}

    dates = _bucket_by_hour([value], 1.0, start)

    assert dates == {datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc): Decimal("1.0")}
    assert "Unexpected time detected" in caplog.text


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


@pytest.mark.asyncio
async def test_collect_dates_returns_empty_when_incremental_fetch_totally_empty():
    importer = _importer(ValueType.DAY)
    importer.async_smartmeter.get_bewegungsdaten.return_value = _data(None)

    dates = await importer._collect_dates(START, END, recover_quarter_hour=False)

    assert dates == {}


@pytest.mark.asyncio
async def test_import_statistics_rejects_naive_start():
    importer = _importer(ValueType.QUARTER_HOUR)

    with pytest.raises(ValueError):
        await importer._import_statistics(start=datetime(2024, 1, 1), end=END)


@pytest.mark.asyncio
async def test_import_statistics_returns_none_when_start_after_end():
    importer = _importer(ValueType.QUARTER_HOUR)

    result = await importer._import_statistics(start=END, end=START)

    assert result is None
    importer.async_smartmeter.get_bewegungsdaten.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_statistics_returns_none_when_nothing_to_import():
    importer = _importer(ValueType.QUARTER_HOUR)
    importer.async_smartmeter.get_bewegungsdaten.return_value = _data("KWH", [])

    result = await importer._import_statistics(start=START, end=END)

    assert result is None


@pytest.mark.asyncio
async def test_import_statistics_writes_accumulated_statistics():
    importer = _importer(ValueType.QUARTER_HOUR)
    reading = _value(START, 4.0)
    importer.async_smartmeter.get_bewegungsdaten.return_value = _data("KWH", [reading])

    with patch("wnsm.importer.async_add_external_statistics") as write:
        total = await importer._import_statistics(start=START, end=END, total_usage=Decimal("10"))

    assert total == Decimal("14.0")
    write.assert_called_once()
    _hass_arg, _metadata, statistics = write.call_args.args
    assert statistics == [StatisticData(start=START, sum=Decimal("14.0"), state=4.0)]


def test_get_statistics_metadata():
    importer = _importer(ValueType.QUARTER_HOUR)

    metadata = importer.get_statistics_metadata()

    assert metadata["statistic_id"] == importer.id
    assert metadata["name"] == ZAEHLPUNKT
    assert metadata["unit_of_measurement"] == "kWh"
    assert metadata["has_sum"] is True


@pytest.mark.parametrize(("last_inserted_stat", "expected"), [
    pytest.param({"wnsm:x": [{"sum": "1.0", "end": 1.0}]}, True, id="valid"),
    pytest.param({}, False, id="empty"),
    pytest.param({"wnsm:x": [{"sum": "1.0"}]}, False, id="missing_end"),
    pytest.param({"wnsm:x": [{"end": 1.0}]}, False, id="missing_sum"),
    pytest.param({"wnsm:x": [], "wnsm:y": []}, False, id="wrong_key_count"),
])
def test_is_last_inserted_stat_valid(last_inserted_stat, expected):
    importer = _importer(ValueType.QUARTER_HOUR)
    importer.id = "wnsm:x"

    assert importer.is_last_inserted_stat_valid(last_inserted_stat) is expected


def test_prepare_start_off_point_parses_float_timestamp_and_returns_sum():
    importer = _importer(ValueType.QUARTER_HOUR)
    old_end = datetime.now(timezone.utc) - timedelta(days=2)
    last_inserted_stat = {importer.id: [{"sum": "12.5", "end": old_end.timestamp()}]}

    result = importer.prepare_start_off_point(last_inserted_stat)

    assert result is not None
    start, total = result
    assert total == Decimal("12.5")
    assert abs((start - old_end).total_seconds()) < 1


def test_prepare_start_off_point_parses_string_timestamp():
    importer = _importer(ValueType.QUARTER_HOUR)
    old_end = datetime.now(timezone.utc) - timedelta(days=2)
    last_inserted_stat = {importer.id: [{"sum": "1.0", "end": old_end.isoformat()}]}

    result = importer.prepare_start_off_point(last_inserted_stat)

    assert result is not None


def test_prepare_start_off_point_returns_none_when_within_24_hours():
    importer = _importer(ValueType.QUARTER_HOUR)
    recent_end = datetime.now(timezone.utc) - timedelta(hours=1)
    last_inserted_stat = {importer.id: [{"sum": "1.0", "end": recent_end}]}

    assert importer.prepare_start_off_point(last_inserted_stat) is None


def test_prepare_start_off_point_returns_none_for_unparseable_end():
    importer = _importer(ValueType.QUARTER_HOUR)
    last_inserted_stat = {importer.id: [{"sum": "1.0", "end": ["not", "a", "date"]}]}

    assert importer.prepare_start_off_point(last_inserted_stat) is None


@pytest.mark.asyncio
async def test_async_import_runs_initial_import_when_no_previous_stats():
    importer = _importer(ValueType.QUARTER_HOUR)
    importer.async_smartmeter.is_active = MagicMock(return_value=True)
    importer._initial_import_statistics = AsyncMock(return_value=Decimal("1.0"))
    importer._incremental_import_statistics = AsyncMock()

    with patch("wnsm.importer.get_instance") as get_instance:
        get_instance.return_value.async_add_executor_job = AsyncMock(return_value={})
        await importer.async_import()

    importer._initial_import_statistics.assert_awaited_once()
    importer._incremental_import_statistics.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_import_runs_incremental_import_when_previous_stats_are_valid():
    importer = _importer(ValueType.QUARTER_HOUR)
    importer.async_smartmeter.is_active = MagicMock(return_value=True)
    importer._initial_import_statistics = AsyncMock()
    importer._incremental_import_statistics = AsyncMock(return_value=Decimal("2.0"))
    old_end = datetime.now(timezone.utc) - timedelta(days=2)
    valid_stat = {importer.id: [{"sum": "1.0", "end": old_end}]}

    with patch("wnsm.importer.get_instance") as get_instance:
        get_instance.return_value.async_add_executor_job = AsyncMock(return_value=valid_stat)
        await importer.async_import()

    importer._initial_import_statistics.assert_not_awaited()
    importer._incremental_import_statistics.assert_awaited_once()
    assert importer._incremental_import_statistics.call_args.args[1] == Decimal("1.0")


@pytest.mark.asyncio
async def test_async_import_skips_inactive_zaehlpunkt():
    importer = _importer(ValueType.QUARTER_HOUR)
    importer.async_smartmeter.is_active = MagicMock(return_value=False)
    importer._initial_import_statistics = AsyncMock()

    with patch("wnsm.importer.get_instance") as get_instance:
        get_instance.return_value.async_add_executor_job = AsyncMock(return_value={})
        await importer.async_import()

    importer._initial_import_statistics.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_import_skips_incremental_when_within_24_hours():
    importer = _importer(ValueType.QUARTER_HOUR)
    importer.async_smartmeter.is_active = MagicMock(return_value=True)
    importer._incremental_import_statistics = AsyncMock()
    recent_stat = {importer.id: [{"sum": "1.0", "end": datetime.now(timezone.utc) - timedelta(hours=1)}]}

    with patch("wnsm.importer.get_instance") as get_instance:
        get_instance.return_value.async_add_executor_job = AsyncMock(return_value=recent_stat)
        await importer.async_import()

    importer._incremental_import_statistics.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_import_logs_timeout_error():
    importer = _importer(ValueType.QUARTER_HOUR)
    importer.async_smartmeter.login = AsyncMock(side_effect=TimeoutError("slow"))

    with patch("wnsm.importer.get_instance") as get_instance:
        get_instance.return_value.async_add_executor_job = AsyncMock(return_value={})
        await importer.async_import()  # must not raise


@pytest.mark.asyncio
async def test_async_import_logs_smartmeter_error_with_response_body():
    from wnsm.api.errors import SmartmeterError

    importer = _importer(ValueType.QUARTER_HOUR)
    importer.async_smartmeter.login = AsyncMock(side_effect=SmartmeterError("boom", error_response="body"))

    with patch("wnsm.importer.get_instance") as get_instance:
        get_instance.return_value.async_add_executor_job = AsyncMock(return_value={})
        await importer.async_import()  # must not raise


@pytest.mark.asyncio
async def test_async_import_logs_runtime_error_without_response_body():
    importer = _importer(ValueType.QUARTER_HOUR)
    importer.async_smartmeter.login = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("wnsm.importer.get_instance") as get_instance:
        get_instance.return_value.async_add_executor_job = AsyncMock(return_value={})
        await importer.async_import()  # must not raise


@pytest.mark.asyncio
async def test_initial_import_statistics_recovers_quarter_hour():
    importer = _importer(ValueType.QUARTER_HOUR)
    importer._import_statistics = AsyncMock(return_value=Decimal("1.0"))

    result = await importer._initial_import_statistics()

    assert result == Decimal("1.0")
    importer._import_statistics.assert_awaited_once_with(recover_quarter_hour=True)


@pytest.mark.asyncio
async def test_incremental_import_statistics_forwards_start_and_total():
    importer = _importer(ValueType.QUARTER_HOUR)
    importer._import_statistics = AsyncMock(return_value=Decimal("2.0"))

    result = await importer._incremental_import_statistics(START, Decimal("1.0"))

    assert result == Decimal("2.0")
    importer._import_statistics.assert_awaited_once_with(start=START, total_usage=Decimal("1.0"))
