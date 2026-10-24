"""WNSMSensor tests"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wnsm.api.constants import AnlagenType
from wnsm.wnsm_sensor import WNSMSensor, eeg_splits


def test_eeg_splits_consumption():
    assert eeg_splits(AnlagenType.CONSUMING.value) == (
        ("_grid", "G001", None),
        ("_eeg", "G003", None),
    )


def test_eeg_splits_feeding():
    assert eeg_splits(AnlagenType.FEEDING.value) == (
        ("_grid", "U001", None),
        ("_eeg", "E002", "U001"),
    )


def test_eeg_splits_unknown_type_falls_back_to_consumption():
    assert eeg_splits(None)[1] == ("_eeg", "G003", None)


async def _update(zaehlpunkt_type: str, eeg: bool):
    async_smartmeter = MagicMock()
    async_smartmeter.login = AsyncMock()
    async_smartmeter.get_zaehlpunkt = AsyncMock(return_value={"type": zaehlpunkt_type, "granularity": "QUARTER_HOUR"})
    async_smartmeter.is_active.return_value = True
    async_smartmeter.get_meter_reading_from_historic_data = AsyncMock(return_value=42.0)
    async_smartmeter.has_energiegemeinschaft = AsyncMock(return_value=eeg)
    sensor = WNSMSensor("user", "pass", "AT001")
    sensor.hass = MagicMock()
    with patch("wnsm.wnsm_sensor.Smartmeter"), \
            patch("wnsm.wnsm_sensor.AsyncSmartmeter", return_value=async_smartmeter), \
            patch("wnsm.wnsm_sensor.Importer") as importer:
        importer.return_value.async_import = AsyncMock()
        await sensor.async_update()
    return sensor, importer


@pytest.mark.asyncio
async def test_async_update_imports_feed_in_split_for_eeg():
    sensor, importer = await _update(AnlagenType.FEEDING.value, eeg=True)

    assert sensor.available
    assert importer.call_count == 3
    splits = [(c.kwargs["statistic_suffix"], c.kwargs["rolle"], c.kwargs["subtract_rolle"]) for c in importer.call_args_list[1:]]
    assert splits == [("_grid", "U001", None), ("_eeg", "E002", "U001")]


@pytest.mark.asyncio
async def test_async_update_without_eeg_imports_only_the_total():
    sensor, importer = await _update(AnlagenType.CONSUMING.value, eeg=False)

    assert sensor.available
    assert importer.call_count == 1
