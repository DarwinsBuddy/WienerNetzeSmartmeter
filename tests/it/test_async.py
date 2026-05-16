"""AsyncSmartmeter tests"""
import asyncio

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


class FakeHass:
    """Minimal hass stub: run executor jobs inline."""

    async def async_add_executor_job(self, func, *args):
        return func(*args)


def detect(requests_mock: Mocker, eag_teilnahmen):
    z = zaehlpunkt_response([enabled(zaehlpunkt())])[0]
    zp = z["zaehlpunkte"][0]['zaehlpunktnummer']
    customer_id = z["geschaeftspartner"]
    expect_login(requests_mock)
    expect_zaehlpunkte(requests_mock, [enabled(zaehlpunkt())])
    expect_zaehlwerke(requests_mock, customer_id, zp, eag_teilnahmen=eag_teilnahmen)
    async_smartmeter = AsyncSmartmeter(FakeHass(), smartmeter().login())
    return asyncio.run(async_smartmeter.has_energiegemeinschaft(zp))


@pytest.mark.usefixtures("requests_mock")
def test_has_energiegemeinschaft_active(requests_mock: Mocker):
    assert detect(requests_mock, [{"status": "A", "dateFrom": "2020-01-01", "dateTo": "9999-12-31"}])


@pytest.mark.usefixtures("requests_mock")
def test_has_energiegemeinschaft_missing(requests_mock: Mocker):
    assert not detect(requests_mock, None)


@pytest.mark.usefixtures("requests_mock")
def test_has_energiegemeinschaft_status_not_active(requests_mock: Mocker):
    assert not detect(requests_mock, [{"status": "B", "dateFrom": "2020-01-01", "dateTo": "9999-12-31"}])


@pytest.mark.usefixtures("requests_mock")
def test_has_energiegemeinschaft_expired(requests_mock: Mocker):
    assert not detect(requests_mock, [{"status": "A", "dateFrom": "2020-01-01", "dateTo": "2020-12-31"}])
