'''
    api constants
'''
import re

MAIN_SCRIPT_REGEX = re.compile(r"^main\S+\.js$")
API_GATEWAY_TOKEN_REGEX = re.compile(r'b2cApiKey\:\s*\"([A-Za-z0-9\-_]+)\"', re.IGNORECASE)

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
    '''
    build access token and add kwargs
    '''
    args = {
        "grant_type": "authorization_code",
        "client_id": "wn-smartmeter",
        "redirect_uri": REDIRECT_URI,
    }
    args.update(**kwargs)
    return args


def build_verbrauchs_args(**kwargs):
    '''
    build arguments for verbrauchs call and add kwargs
    '''
    args = {
        "period": "DAY",
        "accumulate": False,
        "offset": 0,
        "dayViewResolution": "QUARTER-HOUR",
    }
    args.update(**kwargs)
    return args
