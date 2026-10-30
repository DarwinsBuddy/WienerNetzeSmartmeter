"""AsyncSmartmeter tests"""
from unittest.mock import MagicMock

import pytest
from requests_mock import Mocker

from it import (
    expect_login,
    expect_zaehlpunkte,
    expect_zaehlwerke,
    smartmeter,
    zaehlpunkt,
    zaehlpunkt_response,
    enabled,
)
from wnsm.AsyncSmartmeter import AsyncSmartmeter
from wnsm.api.constants import ValueType
from wnsm.api.errors import SmartmeterConnectionError


class FakeHass:
    """Minimal hass stub: run executor jobs inline."""

    async def async_add_executor_job(self, func, *args):
        return func(*args)


async def detect(requests_mock: Mocker, eag_teilnahmen):
    z = zaehlpunkt_response([enabled(zaehlpunkt())])[0]
    zp = z["zaehlpunkte"][0]['zaehlpunktnummer']
    customer_id = z["geschaeftspartner"]
    expect_login(requests_mock)
    expect_zaehlpunkte(requests_mock, [enabled(zaehlpunkt())])
    expect_zaehlwerke(requests_mock, customer_id, zp, eag_teilnahmen=eag_teilnahmen)
    async_smartmeter = AsyncSmartmeter(FakeHass(), smartmeter().login())
    return await async_smartmeter.has_energiegemeinschaft(zp)


@pytest.mark.asyncio
@pytest.mark.usefixtures("requests_mock")
async def test_has_energiegemeinschaft_active(requests_mock: Mocker):
    assert await detect(requests_mock, [{"status": "A", "dateFrom": "2020-01-01", "dateTo": "9999-12-31"}])


@pytest.mark.asyncio
@pytest.mark.usefixtures("requests_mock")
async def test_has_energiegemeinschaft_missing(requests_mock: Mocker):
    assert not await detect(requests_mock, None)


@pytest.mark.asyncio
@pytest.mark.usefixtures("requests_mock")
async def test_has_energiegemeinschaft_status_not_active(requests_mock: Mocker):
    assert not await detect(requests_mock, [{"status": "B", "dateFrom": "2020-01-01", "dateTo": "9999-12-31"}])


@pytest.mark.asyncio
@pytest.mark.usefixtures("requests_mock")
async def test_has_energiegemeinschaft_expired(requests_mock: Mocker):
    assert not await detect(requests_mock, [{"status": "A", "dateFrom": "2020-01-01", "dateTo": "2020-12-31"}])


@pytest.mark.asyncio
@pytest.mark.usefixtures("requests_mock")
async def test_has_energiegemeinschaft_skips_malformed_entries(requests_mock: Mocker):
    assert await detect(requests_mock, [
        {"status": "A", "dateFrom": "not-a-date", "dateTo": "9999-12-31"},
        {"status": "A", "dateFrom": "2020-01-01"},
        {"status": "A", "dateFrom": "2020-01-01", "dateTo": "9999-12-31"},
    ])


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("boom"), SmartmeterConnectionError("token expired"), ValueError("no json")])
async def test_has_energiegemeinschaft_never_raises(error):
    sm = MagicMock()
    sm.zaehlwerke.side_effect = error

    assert not await AsyncSmartmeter(FakeHass(), sm).has_energiegemeinschaft("AT001")


@pytest.mark.asyncio
async def test_get_zaehlwerke_raises_on_exception_response():
    sm = MagicMock()
    sm.zaehlwerke.return_value = {"Exception": "something went wrong"}

    with pytest.raises(RuntimeError):
        await AsyncSmartmeter(FakeHass(), sm).get_zaehlwerke("AT001")


@pytest.mark.asyncio
async def test_get_bewegungsdaten_passes_role():
    sm = MagicMock()
    sm.bewegungsdaten.return_value = {"descriptor": {"einheit": "KWH", "rolle": "G003"}, "values": []}

    result = await AsyncSmartmeter(FakeHass(), sm).get_bewegungsdaten("AT001", None, None, ValueType.QUARTER_HOUR, "G003")

    sm.bewegungsdaten.assert_called_once_with("AT001", None, None, ValueType.QUARTER_HOUR, None, "G003")
    assert result["unitOfMeasurement"] == "KWH"
    assert result["role"] == "G003"
