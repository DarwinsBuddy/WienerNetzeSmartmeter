"""API tests"""
import pytest
import time
from requests_mock import Mocker
import datetime as dt

from it import (
    expect_login,
    expect_verbrauch_raw,
    smartmeter,
    expect_zaehlpunkte,
    verbrauch_raw_response,
    zaehlpunkt,
    enabled,
    disabled,
    mock_login_page,
    mock_authenticate,
    PASSWORD,
    USERNAME,
    mock_token,
    mock_get_api_key,
    expect_history,
)
from wnsm.api.errors import SmartmeterConnectionError, SmartmeterLoginError


@pytest.mark.usefixtures("requests_mock")
def test_successful_login(requests_mock: Mocker):
    expect_login(requests_mock)

    smartmeter().login()
    assert True


@pytest.mark.usefixtures("requests_mock")
def test_unsuccessful_login_failing_on_login_page_load(requests_mock):
    mock_login_page(requests_mock, 404)
    with pytest.raises(SmartmeterConnectionError) as exc_info:
        smartmeter().login()
    assert 'Could not load login page. Error: ' in str(exc_info.value)


@pytest.mark.usefixtures("requests_mock")
def test_unsuccessful_login_failing_on_connection_timeout_while_login_page_load(requests_mock):
    mock_login_page(requests_mock, None)
    with pytest.raises(SmartmeterConnectionError) as exc_info:
        smartmeter().login()
    assert 'Could not load login page' in str(exc_info.value)


@pytest.mark.usefixtures("requests_mock")
def test_unsuccessful_login_failing_on_connection_timeout(requests_mock):
    mock_login_page(requests_mock)
    mock_authenticate(requests_mock, USERNAME, PASSWORD, status=None)
    with pytest.raises(SmartmeterConnectionError) as exc_info:
        smartmeter().login()
    assert 'Could not login with credentials' in str(exc_info.value)


@pytest.mark.usefixtures("requests_mock")
def test_unsuccessful_login_failing_on_credentials_login(requests_mock):
    mock_login_page(requests_mock)
    mock_authenticate(requests_mock, USERNAME, "WrongPassword", status=403)
    with pytest.raises(SmartmeterLoginError) as exc_info:
        smartmeter(username=USERNAME, password="WrongPassword").login()
    assert 'Login failed. Check username/password.' in str(exc_info.value)


@pytest.mark.usefixtures("requests_mock")
def test_unsuccessful_login_failing_on_non_bearer_token(requests_mock):
    mock_login_page(requests_mock)
    mock_authenticate(requests_mock, USERNAME, PASSWORD)
    mock_token(requests_mock, token_type="IAmNotABearerToken")
    with pytest.raises(SmartmeterLoginError) as exc_info:
        smartmeter(username=USERNAME, password=PASSWORD).login()
    assert 'Bearer token required' in str(exc_info.value)


@pytest.mark.usefixtures("requests_mock")
def test_unsuccessful_login_failing_on_redirect_when_location_header_does_not_bear_code(requests_mock):
    mock_login_page(requests_mock)
    mock_authenticate(requests_mock, USERNAME, PASSWORD, status=404)
    with pytest.raises(SmartmeterLoginError) as exc_info:
        smartmeter().login()
    assert "Login failed. Could not extract 'code' from 'Location'" in str(exc_info.value)


@pytest.mark.usefixtures("requests_mock")
def test_unsuccessful_login_failing_on_connection_timeout_while_retrieving_access_token(requests_mock):
    mock_login_page(requests_mock)
    mock_authenticate(requests_mock, USERNAME, PASSWORD)
    mock_token(requests_mock, status=None)
    with pytest.raises(SmartmeterConnectionError) as exc_info:
        smartmeter().login()
    assert 'Could not obtain access token' == str(exc_info.value)


@pytest.mark.usefixtures("requests_mock")
def test_unsuccessful_login_failing_on_empty_response_while_retrieving_access_token(requests_mock):
    mock_login_page(requests_mock)
    mock_authenticate(requests_mock, USERNAME, PASSWORD)
    mock_token(requests_mock, status=404)
    with pytest.raises(SmartmeterConnectionError) as exc_info:
        smartmeter().login()
    assert 'Could not obtain access token: ' in str(exc_info.value)


@pytest.mark.usefixtures("requests_mock")
def test_unsuccessful_login_failing_on_connection_timeout_while_get_page_on_get_api_key(requests_mock):
    mock_login_page(requests_mock)
    mock_authenticate(requests_mock, USERNAME, PASSWORD)
    mock_token(requests_mock)
    mock_get_api_key(requests_mock, get_page_status=None)
    with pytest.raises(SmartmeterConnectionError) as exc_info:
        smartmeter().login()
    assert 'Could not obtain API key' == str(exc_info.value)


@pytest.mark.usefixtures("requests_mock")
def test_unsuccessful_login_failing_on_connection_timeout_while_get_main_js_on_get_api_key(requests_mock):
    mock_login_page(requests_mock)
    mock_authenticate(requests_mock, USERNAME, PASSWORD)
    mock_token(requests_mock)
    mock_get_api_key(requests_mock, get_main_js_status=None)
    with pytest.raises(SmartmeterConnectionError) as exc_info:
        smartmeter().login()
    assert 'Could not obtain API Key from scripts' == str(exc_info.value)


@pytest.mark.usefixtures("requests_mock")
def test_unsuccessful_login_failing_on_invalid_script_while_get_main_js_on_get_api_key(requests_mock):
    mock_login_page(requests_mock)
    mock_authenticate(requests_mock, USERNAME, PASSWORD)
    mock_token(requests_mock)
    mock_get_api_key(requests_mock, get_main_js_status=404)
    with pytest.raises(SmartmeterConnectionError) as exc_info:
        smartmeter().login()
    assert 'Could not obtain API Key - no match' == str(exc_info.value)


@pytest.mark.usefixtures("requests_mock")
def test_access_key_expired(requests_mock):
    mock_login_page(requests_mock)
    mock_authenticate(requests_mock, USERNAME, PASSWORD)
    mock_token(requests_mock, expires=1)
    mock_get_api_key(requests_mock)
    sm = smartmeter(username=USERNAME, password=PASSWORD).login()
    time.sleep(2)
    with pytest.raises(SmartmeterConnectionError) as exc_info:
        sm._access_valid_or_raise()
    assert 'Access Token is not valid anymore' in str(exc_info.value)


@pytest.mark.usefixtures("requests_mock")
def test_zaehlpunkte(requests_mock: Mocker):
    expect_login(requests_mock)
    expect_zaehlpunkte(requests_mock, [enabled(zaehlpunkt()), disabled(zaehlpunkt())])

    zps = smartmeter().login().zaehlpunkte()
    assert 2 == len(zps[0]['zaehlpunkte'])
    assert zps[0]['zaehlpunkte'][0]['isActive']
    assert not zps[0]['zaehlpunkte'][1]['isActive']


@pytest.mark.usefixtures("requests_mock")
def test_history(requests_mock: Mocker):
    expect_login(requests_mock)
    expect_history(requests_mock, enabled(zaehlpunkt())['zaehlpunktnummer'])
    expect_zaehlpunkte(requests_mock, [enabled(zaehlpunkt())])

    hist = smartmeter().login().historical_data()

    assert 1 == len(hist['messwerte'])
    assert 'WH' == hist['einheit']

@pytest.mark.usefixtures("requests_mock")
def test_verbrauch_raw(requests_mock: Mocker):

    dateFrom = dt.datetime(2023, 4, 21, 22, 00, 00)
    dateTo   = dt.datetime(2023, 5,  1, 21, 59, 59)
    zp       = "AT000000001234567890"
    valid_verbrauch_raw_response = verbrauch_raw_response()
    expect_login(requests_mock)
    expect_history(requests_mock, enabled(zaehlpunkt())['zaehlpunktnummer'])
    expect_zaehlpunkte(requests_mock, [enabled(zaehlpunkt())])
    expect_verbrauch_raw(requests_mock, zp, dateFrom, dateTo, valid_verbrauch_raw_response)

    verbrauch = smartmeter().login().verbrauch_raw(dateFrom, dateTo, zp)

    assert 7 == len(verbrauch['values'])
