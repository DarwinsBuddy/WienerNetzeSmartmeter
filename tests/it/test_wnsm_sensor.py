"""Tests for WNSMSensor.async_update."""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import it  # noqa: F401
from wnsm.wnsm_sensor import WNSMSensor

ZAEHLPUNKT = "AT0010000000000000001000011111111"


async def _update(wnsm_sensor: WNSMSensor) -> MagicMock:
    with patch("wnsm.wnsm_sensor.Smartmeter"), \
            patch("wnsm.wnsm_sensor.AsyncSmartmeter") as async_smartmeter_cls, \
            patch("wnsm.wnsm_sensor.Importer") as importer_cls:
        async_smartmeter = async_smartmeter_cls.return_value
        async_smartmeter.login = AsyncMock()
        async_smartmeter.get_zaehlpunkt = AsyncMock(return_value={"type": "TAGSTROM"})
        async_smartmeter.is_active = MagicMock(return_value=True)
        async_smartmeter.get_meter_reading_from_historic_data = AsyncMock(return_value=1.0)
        importer_cls.return_value.async_import = AsyncMock()
        await wnsm_sensor.async_update()
    return importer_cls


@pytest.mark.asyncio
async def test_async_update_passes_prices_to_importer():
    wnsm_sensor = WNSMSensor("user", "secret", ZAEHLPUNKT,
                             price_per_kwh=Decimal("0.25"), feed_in_price_per_kwh=Decimal("0.08"))

    importer_cls = await _update(wnsm_sensor)

    assert importer_cls.call_args.kwargs == {"price_per_kwh": Decimal("0.25"), "feed_in_price_per_kwh": Decimal("0.08")}
    importer_cls.return_value.async_import.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_update_without_prices_passes_none_to_importer():
    wnsm_sensor = WNSMSensor("user", "secret", ZAEHLPUNKT)

    importer_cls = await _update(wnsm_sensor)

    assert importer_cls.call_args.kwargs == {"price_per_kwh": None, "feed_in_price_per_kwh": None}
