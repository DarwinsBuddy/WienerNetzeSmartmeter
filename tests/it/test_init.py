"""Config entry setup and unload tests"""
from unittest.mock import AsyncMock, MagicMock

import pytest

import it  # noqa: F401  # puts custom_components on sys.path
from wnsm import async_setup_entry, async_unload_entry


def _hass(unload_ok: bool = True) -> MagicMock:
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=unload_ok)
    return hass


def _entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry"
    entry.data = {"username": "user"}
    return entry


@pytest.mark.asyncio
async def test_setup_entry_stores_data_under_wnsm_domain():
    hass, entry = _hass(), _entry()

    assert await async_setup_entry(hass, entry)

    assert hass.data["wnsm"] == {"entry": {"username": "user"}}
    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, ["sensor"])


@pytest.mark.asyncio
async def test_unload_entry_unloads_sensor_platform_and_removes_data():
    hass, entry = _hass(), _entry()
    await async_setup_entry(hass, entry)

    assert await async_unload_entry(hass, entry)

    hass.config_entries.async_unload_platforms.assert_awaited_once_with(entry, ["sensor"])
    assert hass.data["wnsm"] == {}


@pytest.mark.asyncio
async def test_failed_unload_keeps_data():
    hass, entry = _hass(unload_ok=False), _entry()
    await async_setup_entry(hass, entry)

    assert not await async_unload_entry(hass, entry)

    assert hass.data["wnsm"] == {"entry": {"username": "user"}}
