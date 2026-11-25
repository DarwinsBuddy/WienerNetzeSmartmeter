"""Tests for the price sensor option: options flow, entry setup and sensor wiring."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType

import wnsm
from wnsm import sensor
from wnsm.config_flow import WienerNetzeSmartMeterCustomConfigFlow, WNSMOptionsFlowHandler
from wnsm.const import CONF_PRICE_ENTITY, CONF_ZAEHLPUNKTE, DOMAIN

ENTRY_ID = "entry-1"
PRICE_ENTITY = "sensor.electricity_price"
ENTRY_DATA = {
    CONF_USERNAME: "user",
    CONF_PASSWORD: "pass",
    CONF_ZAEHLPUNKTE: [{"zaehlpunktnummer": "AT001"}, {"zaehlpunktnummer": "AT002"}],
}


def _entry(options: dict) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = ENTRY_ID
    entry.data = ENTRY_DATA
    entry.options = options
    return entry


def _options_flow(options: dict) -> WNSMOptionsFlowHandler:
    flow = WienerNetzeSmartMeterCustomConfigFlow.async_get_options_flow(_entry(options))
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_known_entry.return_value = _entry(options)
    flow.handler = ENTRY_ID
    return flow


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_reload = AsyncMock()
    return hass


@pytest.mark.asyncio
async def test_options_flow_shows_form_with_current_price_entity():
    result = await _options_flow({CONF_PRICE_ENTITY: PRICE_ENTITY}).async_step_init()

    assert result["type"] == FlowResultType.FORM
    (key,) = result["data_schema"].schema
    assert key.schema == CONF_PRICE_ENTITY
    assert key.description == {"suggested_value": PRICE_ENTITY}


@pytest.mark.asyncio
async def test_options_flow_saves_selected_price_entity():
    result = await _options_flow({}).async_step_init({CONF_PRICE_ENTITY: PRICE_ENTITY})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_PRICE_ENTITY: PRICE_ENTITY}


@pytest.mark.asyncio
async def test_async_setup_entry_stores_data_and_options_under_wnsm_domain():
    hass = _hass()
    entry = _entry({CONF_PRICE_ENTITY: PRICE_ENTITY})

    assert await wnsm.async_setup_entry(hass, entry) is True

    assert hass.data[DOMAIN][ENTRY_ID] == {**ENTRY_DATA, "options": {CONF_PRICE_ENTITY: PRICE_ENTITY}}


@pytest.mark.asyncio
async def test_options_update_reloads_entry():
    hass = _hass()
    entry = _entry({})
    await wnsm.async_setup_entry(hass, entry)
    listener = entry.add_update_listener.call_args.args[0]

    await listener(hass, entry)

    hass.config_entries.async_reload.assert_awaited_once_with(ENTRY_ID)


@pytest.mark.asyncio
@pytest.mark.parametrize("options, expected", [
    ({}, None),
    ({CONF_PRICE_ENTITY: ""}, None),
    ({CONF_PRICE_ENTITY: PRICE_ENTITY}, PRICE_ENTITY),
])
async def test_sensor_setup_entry_passes_price_entity_to_each_sensor(options, expected):
    hass = _hass()
    hass.data = {DOMAIN: {ENTRY_ID: {**ENTRY_DATA, "options": options}}}
    add_entities = MagicMock()

    await sensor.async_setup_entry(hass, _entry(options), add_entities)

    sensors = add_entities.call_args.args[0]
    assert [s.price_entity_id for s in sensors] == [expected, expected]
