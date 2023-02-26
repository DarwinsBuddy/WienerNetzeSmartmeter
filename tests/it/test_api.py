"""API tests"""
import pytest
from requests_mock import Mocker

from it import expect_login, smartmeter, expect_zaehlpunkte, zaehlpunkt, enabled, disabled


@pytest.mark.usefixtures("requests_mock")
def test_login(requests_mock: Mocker):
    expect_login(requests_mock)

    smartmeter().login()
    assert True


@pytest.mark.usefixtures("requests_mock")
def test_zaehlpunkte(requests_mock: Mocker):
    expect_login(requests_mock)
    expect_zaehlpunkte(requests_mock, [enabled(zaehlpunkt()), disabled(zaehlpunkt())])

    smartmeter().login()
    zps = smartmeter().zaehlpunkte()
    assert 2 == len(zps[0]['zaehlpunkte'])
    assert zps[0]['zaehlpunkte'][0]['isActive']
    assert not zps[0]['zaehlpunkte'][1]['isActive']
