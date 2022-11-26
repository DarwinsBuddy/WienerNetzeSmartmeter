import re

MAIN_SCRIPT_REGEX = re.compile("^main\S+\.js$")
API_GATEWAY_TOKEN_REGEX = re.compile('b2capiKey\:"([A-Za-z0-9-_]+)"')

PAGE_URL = "https://smartmeter-web.wienernetze.at/"
API_URL_ALT = "https://service.wienernetze.at/sm/api/"
API_URL = "https://api.wstw.at/gateway/WN_SMART_METER_PORTAL_API_B2C/1.0/"
REDIRECT_URI = "https://smartmeter-web.wienernetze.at/"
API_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
AUTH_URL = "https://log.wien/auth/realms/logwien/protocol/openid-connect/"  # noqa


LOGIN_ARGS = {
    "client_id": "wn-smartmeter",
    "redirect_uri": REDIRECT_URI,
    "response_mode": "fragment",
    "response_type": "code",
    "scope": "openid",
    "nonce": "",
}


def build_access_token_args(**kwargs):
    args = {
        "grant_type": "authorization_code",
        "client_id": "wn-smartmeter",
        "redirect_uri": REDIRECT_URI,
    }
    args.update(**kwargs)
    return args


def build_verbrauchs_args(**kwargs):
    args = {
        "period": "DAY",
        "accumulate": False,
        "offset": 0,
        # Possible values:
        # HOUR
        # QUARTER-HOUR
        "dayViewResolution": "HOUR",  # home-assistant can not store 15min anyways
    }
    args.update(**kwargs)
    return args
