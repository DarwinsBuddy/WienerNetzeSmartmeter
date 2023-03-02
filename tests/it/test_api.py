"""API tests"""
import pytest
from requests_mock import Mocker

from it import expect_login, smartmeter, expect_zaehlpunkte, zaehlpunkt, enabled, disabled, mock_login_page, \
    mock_authenticate, PASSWORD, USERNAME, mock_token, mock_get_api_key
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
def test_zaehlpunkte(requests_mock: Mocker):
    expect_login(requests_mock)
    expect_zaehlpunkte(requests_mock, [enabled(zaehlpunkt()), disabled(zaehlpunkt())])

    smartmeter().login()
    zps = smartmeter().zaehlpunkte()
    assert 2 == len(zps[0]['zaehlpunkte'])
    assert zps[0]['zaehlpunkte'][0]['isActive']
    assert not zps[0]['zaehlpunkte'][1]['isActive']
