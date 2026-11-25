"""Tests for the cost statistics that Importer computes from a price sensor."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wnsm.api.constants import ValueType
from wnsm.importer import Importer

ZAEHLPUNKT = "AT0010000000000000001000011111111"
PRICE_ENTITY = "sensor.electricity_price"
START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime(2024, 1, 2, tzinfo=timezone.utc)
H0 = START
H1 = START + timedelta(hours=1)
H2 = START + timedelta(hours=2)


def _importer(price_entity_id: str | None = PRICE_ENTITY) -> Importer:
    hass = MagicMock()
    hass.states.get.return_value = MagicMock(attributes={"unit_of_measurement": "EUR/kWh"})
    return Importer(
        hass=hass,
        async_smartmeter=AsyncMock(),
        zaehlpunkt=ZAEHLPUNKT,
        unit_of_measurement="kWh",
        granularity=ValueType.QUARTER_HOUR,
        price_entity_id=price_entity_id,
    )


def _patch_executor(*results):
    """Patch get_instance so that each executor job returns the next result."""
    patcher = patch("wnsm.importer.get_instance")
    get_instance = patcher.start()
    get_instance.return_value.async_add_executor_job = AsyncMock(side_effect=list(results))
    return patcher, get_instance


# --- price statistics ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_price_statistics_normalises_timestamps_and_skips_missing_values():
    rows = [
        {"start": H0.timestamp(), "mean": 0.1},  # float timestamp
        {"start": "2024-01-01T01:00:00+00:00", "mean": 0.2},  # string timestamp
        {"start": datetime(2024, 1, 1, 2, 0), "mean": 0.3},  # naive datetime -> UTC
        {"start": H0 + timedelta(hours=3, minutes=30), "mean": 0.4},  # truncated to full hour
        {"start": H0 + timedelta(hours=4), "mean": None},  # no mean -> skipped
        {"start": None, "mean": 0.5},  # no start -> skipped
    ]
    patcher, _ = _patch_executor({PRICE_ENTITY: rows})
    try:
        prices = await _importer()._get_price_statistics(START, END)
    finally:
        patcher.stop()

    assert prices == {H0: 0.1, H1: 0.2, H2: 0.3, H0 + timedelta(hours=3): 0.4}


# --- cost import --------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_cost_statistics_multiplies_hourly_usage_by_hourly_price():
    importer = _importer()
    importer._get_price_statistics = AsyncMock(return_value={H0: 0.10, H1: 0.20})
    energy = {importer.id: [
        {"start": H1.timestamp(), "state": 2.0},
        {"start": "2024-01-01T00:00:00+00:00", "state": 1.0},
        {"start": H2, "state": 5.0},  # no price for this hour -> skipped
    ]}
    patcher, _ = _patch_executor(energy)
    try:
        with patch("wnsm.importer.async_add_external_statistics") as add_stats:
            total = await importer._import_cost_statistics(START, END, Decimal("10"))
    finally:
        patcher.stop()

    # 10 + 1.0 kWh * 0.10 + 2.0 kWh * 0.20
    assert total == Decimal("10.5")
    metadata, statistics = add_stats.call_args.args[1:]
    assert metadata["statistic_id"] == importer.cost_id
    assert metadata["unit_of_measurement"] == "EUR"
    assert [s["start"] for s in statistics] == [H0, H1]
    assert [s["state"] for s in statistics] == pytest.approx([0.1, 0.4])
    assert [s["sum"] for s in statistics] == [Decimal("10.1"), Decimal("10.5")]


@pytest.mark.asyncio
async def test_import_cost_statistics_with_daily_data_uses_price_of_first_hour():
    """Documented limitation: a daily value is multiplied by the price of its first hour only."""
    importer = _importer()
    importer._get_price_statistics = AsyncMock(return_value={H0: 0.10, H1: 0.50, H2: 0.50})
    patcher, _ = _patch_executor({importer.id: [{"start": H0, "state": 24.0}]})
    try:
        with patch("wnsm.importer.async_add_external_statistics"):
            total = await importer._import_cost_statistics(START, END)
    finally:
        patcher.stop()

    assert total == Decimal("2.4")


# --- async_import orchestration -----------------------------------------------

def _orchestration_importer(price_entity_id: str | None = PRICE_ENTITY) -> Importer:
    importer = _importer(price_entity_id=price_entity_id)
    importer.async_smartmeter.is_active = MagicMock(return_value=True)
    importer._initial_import_statistics = AsyncMock(return_value=Decimal("1"))
    importer._incremental_import_statistics = AsyncMock(return_value=Decimal("1"))
    importer._initial_import_cost_statistics = AsyncMock()
    importer._incremental_import_cost_statistics = AsyncMock()
    return importer


@pytest.mark.asyncio
async def test_async_import_without_price_entity_does_not_touch_cost_statistics():
    importer = _orchestration_importer(price_entity_id=None)
    patcher, get_instance = _patch_executor({}, {})
    try:
        await importer.async_import()
    finally:
        patcher.stop()

    # only the two energy queries, no cost query
    assert get_instance.return_value.async_add_executor_job.await_count == 2
    importer._initial_import_cost_statistics.assert_not_awaited()
    importer._incremental_import_cost_statistics.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_import_starts_initial_cost_import_without_cost_statistics():
    importer = _orchestration_importer()
    patcher, _ = _patch_executor({}, {}, {})
    try:
        await importer.async_import()
    finally:
        patcher.stop()

    importer._initial_import_cost_statistics.assert_awaited_once()
    importer._incremental_import_cost_statistics.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_import_runs_initial_cost_import_even_when_energy_is_throttled():
    importer = _orchestration_importer()
    recent = {importer.id: [{"sum": 1.0, "end": datetime.now(timezone.utc) - timedelta(hours=1)}]}
    patcher, _ = _patch_executor(recent, {}, recent)
    try:
        await importer.async_import()
    finally:
        patcher.stop()

    importer._incremental_import_statistics.assert_not_awaited()
    importer._initial_import_cost_statistics.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_import_continues_cost_import_from_last_cost_statistic():
    importer = _orchestration_importer()
    old_end = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=2)
    energy = {importer.id: [{"sum": 1.0, "end": old_end}]}
    cost = {importer.cost_id: [{"sum": 3.0, "end": old_end}]}
    patcher, _ = _patch_executor(energy, cost, energy)
    try:
        await importer.async_import()
    finally:
        patcher.stop()

    importer._incremental_import_cost_statistics.assert_awaited_once_with(old_end, Decimal("3.0"))
    importer._initial_import_cost_statistics.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_import_skips_cost_import_when_last_cost_statistic_is_recent():
    importer = _orchestration_importer()
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    energy = {importer.id: [{"sum": 1.0, "end": recent}]}
    cost = {importer.cost_id: [{"sum": 3.0, "end": recent}]}
    patcher, _ = _patch_executor(energy, cost, energy)
    try:
        await importer.async_import()
    finally:
        patcher.stop()

    importer._initial_import_cost_statistics.assert_not_awaited()
    importer._incremental_import_cost_statistics.assert_not_awaited()
