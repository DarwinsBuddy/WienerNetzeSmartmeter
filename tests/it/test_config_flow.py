"""Tests for the options flow."""
from unittest.mock import MagicMock

import pytest
import voluptuous as vol
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

import it  # noqa: F401
from wnsm.config_flow import WienerNetzeSmartMeterCustomConfigFlow, WienerNetzeSmartMeterOptionsFlow
from wnsm.const import CONF_FEED_IN_PRICE_PER_KWH, CONF_PRICE_PER_KWH, DOMAIN


def _options_flow(options: dict) -> WienerNetzeSmartMeterOptionsFlow:
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options)
    flow = WienerNetzeSmartMeterCustomConfigFlow.async_get_options_flow(entry)
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_known_entry.return_value = entry
    flow.handler = entry.entry_id
    return flow


def _suggested_values(result) -> dict:
    return {str(key): key.description["suggested_value"] for key in result["data_schema"].schema}


@pytest.mark.asyncio
async def test_options_flow_shows_form_without_prices():
    result = await _options_flow({}).async_step_init()

    assert result["type"] == FlowResultType.FORM
    assert _suggested_values(result) == {CONF_PRICE_PER_KWH: None, CONF_FEED_IN_PRICE_PER_KWH: None}


@pytest.mark.asyncio
async def test_options_flow_suggests_current_prices():
    result = await _options_flow({CONF_PRICE_PER_KWH: 0.25, CONF_FEED_IN_PRICE_PER_KWH: 0.08}).async_step_init()

    assert _suggested_values(result) == {CONF_PRICE_PER_KWH: 0.25, CONF_FEED_IN_PRICE_PER_KWH: 0.08}


@pytest.mark.asyncio
async def test_options_flow_stores_prices():
    result = await _options_flow({}).async_step_init({CONF_PRICE_PER_KWH: 0.25})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_PRICE_PER_KWH: 0.25}


@pytest.mark.asyncio
async def test_options_flow_rejects_negative_price():
    result = await _options_flow({}).async_step_init()

    with pytest.raises(vol.Invalid):
        result["data_schema"]({CONF_PRICE_PER_KWH: -1})
