import re
import enum

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


class Resolution(enum.Enum):
    """Possible resolution for consumption data of one day"""
    HOUR = "HOUR"  #: gets consumption data per hour
    QUARTER_HOUR = "QUARTER-HOUR"  #: gets consumption data per 15min


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
        "accumulate": False,  # can be changed to True to get a cum-sum
        "offset": 0,  # additional offset to start cum-sum with
        "dayViewResolution": "HOUR",
    }
    args.update(**kwargs)
    return args
