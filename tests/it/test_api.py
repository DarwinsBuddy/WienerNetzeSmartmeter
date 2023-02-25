import urllib.parse
from importlib.resources import files
from urllib import parse

import pytest
from requests_mock.mocker import Mocker

import test_resources
import testutils
from wnsm import api

USERNAME = "margit.musterfrau@gmail.com"
PASSWORD = "Margit1234!"

RESPONSE_CODE = 'b04c44f7-55c6-4c0e-b2af-e9d9408ded2b.949e0f0d-b447-4208-bfef-273d694dc633.c514bbef-6269-48ca-9991-d7d5cd941213'

ACCESS_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBFbVQzTlI1UHV0TlVhelhaeVdlVXphcEhENzFuTW5BQVFZeU9PUWZYVk0ifQ.eyJleHAiOjE2NzczMTIxODEsImlhdCI6MTY3NzMxMTg4MSwiYXV0aF90aW1lIjoxNjc3MzExODgwLCJqdGkiOiIxMjM0NTY3OC0xMjM0LTEyMzQtMTIzNC0xMjM0NTY3ODkwMTIiLCJpc3MiOiJodHRwczovL2xvZy53aWVuL2F1dGgvcmVhbG1zL2xvZ3dpZW4iLCJhdWQiOiJhY2NvdW50Iiwic3ViIjoiMTIzNDU2NzgtMTIzNC0xMjM0LTEyMzQtMTIzNDU2Nzg5MDEyIiwidHlwIjoiQmVhcmVyIiwiYXpwIjoid24tc21hcnRtZXRlciIsIm5vbmNlIjoiMTIzNDU2NzgtMTIzNC0xMjM0LTEyMzQtMTIzNDU2Nzg5MDEyIiwic2Vzc2lvbl9zdGF0ZSI6IjEyMzQ1Njc4LTEyMzQtMTIzNC0xMjM0LTEyMzQ1Njc4OTAxMiIsImFsbG93ZWQtb3JpZ2lucyI6WyJodHRwczovL3NtYXJ0bWV0ZXItd2ViLndpZW5lcm5ldHplLmF0IiwiaHR0cHM6Ly93d3cud2llbmVybmV0emUuYXQiLCJodHRwOi8vbG9jYWxob3N0OjQyMDAiXSwicmVhbG1fYWNjZXNzIjp7InJvbGVzIjpbImRlZmF1bHQtcm9sZXMtd2xvZ2luIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYWNjb3VudCI6eyJyb2xlcyI6WyJtYW5hZ2UtYWNjb3VudCIsIm1hbmFnZS1hY2NvdW50LWxpbmtzIiwidmlldy1wcm9maWxlIl19fSwic2NvcGUiOiJvcGVuaWQgZW1haWwgcHJvZmlsZSIsInNpZCI6IjEyMzQ1Njc4LTEyMzQtMTIzNC0xMjM0LTEyMzQ1Njc4OTAxMiIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJuYW1lIjoiTWFyZ2l0IE11c3RlcmZyYXUiLCJjb21wYW55IjoiUHJpdmF0IiwicHJlZmVycmVkX3VzZXJuYW1lIjoibWFyZ2l0Lm11c3RlcmZyYXVAZ21haWwuY29tIiwic2FsdXRhdGlvbiI6IkZyYXUiLCJnaXZlbl9uYW1lIjoiTWFyZ2l0IiwibG9jYWxlIjoiZW4iLCJmYW1pbHlfbmFtZSI6Ik11c3RlcmZyYXUiLCJlbWFpbCI6Im1hcmdpdC5tdXN0ZXJmcmF1QGdtYWlsLmNvbSJ9.4x8uJ3LE8i5fnyw5qpTiZbi44hvoIM0MhQMCkmH_RUQ'
REFRESH_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImJkZDFhMDQ0LTgzZWUtNDUzMi1hOTk3LTBkMjI1YzcxNTYyNCJ9.eyJleHAiOjE2NzczMTM2ODEsImlhdCI6MTY3NzMxMTg4MSwianRpIjoiMTIzNDU2NzgtMTIzNC0xMjM0LTEyMzQtMTIzNDU2Nzg5MDEyIiwiaXNzIjoiaHR0cHM6Ly9sb2cud2llbi9hdXRoL3JlYWxtcy9sb2d3aWVuIiwiYXVkIjoiaHR0cHM6Ly9sb2cud2llbi9hdXRoL3JlYWxtcy9sb2d3aWVuIiwic3ViIjoiMTIzNDU2NzgtMTIzNC0xMjM0LTEyMzQtMTIzNDU2Nzg5MDEyIiwidHlwIjoiUmVmcmVzaCIsImF6cCI6InduLXNtYXJ0bWV0ZXIiLCJub25jZSI6IjEyMzQ1Njc4LTEyMzQtMTIzNC0xMjM0LTEyMzQ1Njc4OTAxMiIsInNlc3Npb25fc3RhdGUiOiIxMjM0NTY3OC0xMjM0LTEyMzQtMTIzNC0xMjM0NTY3ODkwMTIiLCJzY29wZSI6Im9wZW5pZCBlbWFpbCBwcm9maWxlIiwic2lkIjoiMTIzNDU2NzgtMTIzNC0xMjM0LTEyMzQtMTIzNDU2Nzg5MDEyIn0.eJ2f9hOGaLFgQmcL0WQDsyt3E92Ri9qmJ4lnhZY_W2o'
ID_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBFbVQzTlI1UHV0TlVhelhaeVdlVXphcEhENzFuTW5BQVFZeU9PUWZYVk0ifQ.eyJleHAiOjE2NzczMTIxODEsImlhdCI6MTY3NzMxMTg4MSwiYXV0aF90aW1lIjoxNjc3MzExODgwLCJqdGkiOiIxMjM0NTY3OC0xMjM0LTEyMzQtMTIzNC0xMjM0NTY3ODkwMTIiLCJpc3MiOiJodHRwczovL2xvZy53aWVuL2F1dGgvcmVhbG1zL2xvZ3dpZW4iLCJhdWQiOiJ3bi1zbWFydG1ldGVyIiwic3ViIjoiMTIzNDU2NzgtMTIzNC0xMjM0LTEyMzQtMTIzNDU2Nzg5MDEyIiwidHlwIjoiSUQiLCJhenAiOiJ3bi1zbWFydG1ldGVyIiwibm9uY2UiOiIxMjM0NTY3OC0xMjM0LTEyMzQtMTIzNC0xMjM0NTY3ODkwMTIiLCJzZXNzaW9uX3N0YXRlIjoiMTIzNDU2NzgtMTIzNC0xMjM0LTEyMzQtMTIzNDU2Nzg5MDEyIiwiYXRfaGFzaCI6ImZRQmFaQU1JVC1ucGktWmxCS1JTdHciLCJzaWQiOiIxMjM0NTY3OC0xMjM0LTEyMzQtMTIzNC0xMjM0NTY3ODkwMTIiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwibmFtZSI6Ik1hcmdpdCBNdXN0ZXJmcmF1IiwicHJlZmVycmVkX3VzZXJuYW1lIjoibWFyZ2l0Lm11c3RlcmZyYXVAZ21haWwuY29tIiwiZ2l2ZW5fbmFtZSI6Ik1hcmdpdCIsImxvY2FsZSI6ImVuIiwiZmFtaWx5X25hbWUiOiJNdXN0ZXJmcmF1IiwiZW1haWwiOiJtYXJnaXQubXVzdGVyZnJhdUBnbWFpbC5jb20ifQ.FBGAMU-bDKorGnIC-douEsKJ3VfwpNRBoeHMtytnow8'


@pytest.fixture
def smartmeter(username=USERNAME, password=PASSWORD):
    return api.client.Smartmeter(username=username, password=password)


def mock_login_page(requests_mock: Mocker):
    """
    mock GET login url from login page (+ session_code + client_id + execution param)
    """
    #files('tests.resources').joinpath('auth.html').read_text()
    get_login_url = testutils.AUTH_URL + "/auth?" + parse.urlencode(testutils.LOGIN_ARGS)
    requests_mock.get(url=get_login_url, text=files(test_resources).joinpath('auth.html').read_text())


def mock_get_api_key(requests_mock: Mocker, bearer_token: str = ACCESS_TOKEN):
    """
    mock GET smartmeter-web.wienernetze.at to retrieve main.XXX.js which carries the b2cApiKey
    """
    requests_mock.get(url=testutils.PAGE_URL, request_headers={"Authorization": f"Bearer {bearer_token}"}, text=files(test_resources).joinpath('smartmeter-web.wienernetze.at.html').read_text())
    other_js_scripts = [
        '/ruxitagentjs_ICA27NVfqrux_10257221222094147.js',
        'assets/custom-elements.min.js',
        'runtime.a5b80c17985e7fbd.js',
        'polyfills.a2b46bd315684fc3.js'
    ]
    for irrelevant_script in other_js_scripts:
        requests_mock.get(url=testutils.PAGE_URL + irrelevant_script, text='//some arbitrary javascript code')
    main_js_name = 'main.8fea0d4d0a6b3710.js'
    requests_mock.get(url=testutils.PAGE_URL + main_js_name, text=files(test_resources).joinpath(main_js_name).read_text())
    return testutils.B2C_API_KEY


def mock_token(requests_mock: Mocker, code=RESPONSE_CODE, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN,
               id_token=ID_TOKEN):
    response = {
        "access_token": access_token,
        "expires_in": 300,
        "refresh_expires_in": 1800,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "id_token": id_token,
        "not-before-policy": 0,
        "session_state": "949e0f0d-b447-4208-bfef-273d694dc633",
        "scope": "openid email profile"
    }
    requests_mock.post(f'{testutils.AUTH_URL}/token', additional_matcher=testutils.post_data_matcher({
        "grant_type": "authorization_code",
        "client_id": "wn-smartmeter",
        "redirect_uri": testutils.REDIRECT_URI,
        "code": code
    }),
                       json=response)


def mock_authenticate(requests_mock: Mocker, username, password, code=RESPONSE_CODE):
    """
    mock POST authenticate call resulting in a 302 Found redirecting to another Location
    """
    authenticate_query_params = {
        "session_code": "SESSION_CODE_PLACEHOLDER",
        "execution": "5939ddcc-efd4-407c-b01c-df8977d522b5",
        "client_id": "wn-smartmeter",
        "tab_id": "6tDgFA2FxbU"
    }
    authenticate_url = f'https://log.wien/auth/realms/logwien/login-actions/authenticate?{urllib.parse.urlencode(authenticate_query_params)}'
    redirect_url = f'{testutils.REDIRECT_URI}/#state=cb142d1b-d8b4-4bf3-8a3e-92544790c5c4' \
                   '&session_state=949e0f0d-b447-4208-bfef-273d694dc633' \
                   f'&code={code}'
    requests_mock.post(authenticate_url, status_code=302,
                       additional_matcher=testutils.post_data_matcher({"username": username, "password": password}),
                       headers={'location': redirect_url}
                       )
    requests_mock.get(redirect_url, text='Some page which loads a js, performing a call to /token')


def expect_login(requests_mock: Mocker, username=USERNAME, password=PASSWORD):
    mock_login_page(requests_mock)
    mock_authenticate(requests_mock, username, password)
    mock_token(requests_mock)
    mock_get_api_key(requests_mock)


def test_login(smartmeter, requests_mock: Mocker):
    expect_login(requests_mock)
    smartmeter.login()
    assert True
