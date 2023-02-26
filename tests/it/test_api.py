"""API tests"""
import pytest
from requests_mock.mocker import Mocker

from test_resources import expect_login, USERNAME, PASSWORD, expect_zaehlpunkte
from wnsm import api


@pytest.fixture
def smartmeter(username=USERNAME, password=PASSWORD):
    return api.client.Smartmeter(username=username, password=password)


def test_login(smartmeter, requests_mock: Mocker):
    expect_login(requests_mock)
    smartmeter.login()
    assert True


def test_zaehlpunkte(smartmeter, requests_mock):
    expect_login(requests_mock)
    smartmeter.login()
    expect_zaehlpunkte(requests_mock)
    zps = smartmeter.zaehlpunkte()
    assert 2 == len(zps[0]['zaehlpunkte'])
    assert zps[0]['zaehlpunkte'][0]['isActive']
    assert not zps[0]['zaehlpunkte'][1]['isActive']
