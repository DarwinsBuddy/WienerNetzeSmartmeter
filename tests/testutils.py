import urllib.parse

import requests

PAGE_URL = "https://smartmeter-web.wienernetze.at/"
API_URL_ALT = "https://service.wienernetze.at/sm/api/"
API_URL = "https://api.wstw.at/gateway/WN_SMART_METER_PORTAL_API_B2C/1.0/"
REDIRECT_URI = "https://smartmeter-web.wienernetze.at/"
API_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
AUTH_URL = "https://log.wien/auth/realms/logwien/protocol/openid-connect"  # noqa
B2C_API_KEY = "afb0be74-6455-44f5-a34d-6994223020ba"
LOGIN_ARGS = {
    "client_id": "wn-smartmeter",
    "redirect_uri": REDIRECT_URI,
    "response_mode": "fragment",
    "response_type": "code",
    "scope": "openid",
    "nonce": "",
}


def post_data_matcher(expected: dict = None):
    if expected is None:
        expected = dict()

    def match(request: requests.PreparedRequest):
        flag = dict(urllib.parse.parse_qsl(request.body)) == expected
        if not flag:
            print(f'ACTUAL:   {dict(urllib.parse.parse_qsl(request.body))}')
            print(f'EXPECTED: {expected}')
        return flag
    return match


def json_matcher(expected: dict = None):
    if expected is None:
        expected = dict()

    def match(request: requests.Request):
        return request.json() == expected
    return match
