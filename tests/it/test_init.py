"""Tests for setting up and unloading the config entry."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

import it  # noqa: F401
from wnsm import async_setup_entry, async_unload_entry
from wnsm import sensor
from wnsm.const import CONF_ZAEHLPUNKTE, DOMAIN

ZAEHLPUNKT = "AT0010000000000000001000011111111"
ENTRY_DATA = {
    CONF_USERNAME: "user",
    CONF_PASSWORD: "secret",
    CONF_ZAEHLPUNKTE: [{"zaehlpunktnummer": ZAEHLPUNKT}],
}


def _hass(unload_ok: bool = True) -> MagicMock:
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=unload_ok)
    return hass


def _entry() -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)


@pytest.mark.asyncio
async def test_setup_entry_stores_data_under_integration_domain():
    hass = _hass()
    entry = _entry()

    assert await async_setup_entry(hass, entry) is True

    assert hass.data == {DOMAIN: {entry.entry_id: ENTRY_DATA}}
    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, ["sensor"])


@pytest.mark.asyncio
async def test_unload_entry_unloads_platforms_and_removes_data():
    hass = _hass()
    entry = _entry()
    await async_setup_entry(hass, entry)

    assert await async_unload_entry(hass, entry) is True

    hass.config_entries.async_unload_platforms.assert_awaited_once_with(entry, ["sensor"])
    assert hass.data[DOMAIN] == {}


@pytest.mark.asyncio
async def test_unload_entry_keeps_data_when_platform_unload_fails():
    hass = _hass(unload_ok=False)
    entry = _entry()
    await async_setup_entry(hass, entry)

    assert await async_unload_entry(hass, entry) is False

    assert hass.data[DOMAIN] == {entry.entry_id: ENTRY_DATA}


@pytest.mark.asyncio
async def test_sensor_setup_entry_reads_data_from_integration_domain():
    hass = _hass()
    entry = _entry()
    hass.data = {DOMAIN: {entry.entry_id: ENTRY_DATA}}
    add_entities = MagicMock()

    await sensor.async_setup_entry(hass, entry, add_entities)

    sensors = add_entities.call_args.args[0]
    assert [s.zaehlpunkt for s in sensors] == [ZAEHLPUNKT]


@pytest.mark.asyncio
async def test_sensor_setup_platform_creates_sensor_from_yaml_config():
    add_entities = MagicMock()

    await sensor.async_setup_platform(_hass(), {**ENTRY_DATA, "device_id": ZAEHLPUNKT}, add_entities)

    sensors = add_entities.call_args.args[0]
    assert [s.zaehlpunkt for s in sensors] == [ZAEHLPUNKT]
