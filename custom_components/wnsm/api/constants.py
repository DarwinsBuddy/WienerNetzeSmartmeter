import enum

PAGE_URL = "https://smartmeter-web.wienernetze.at/"
API_CONFIG_URL = "https://smartmeter-web.wienernetze.at/assets/app-config.json"
API_URL_ALT = "https://service.wienernetze.at/sm/api/"

API_URL = "https://api.wstw.at/gateway/WN_SMART_METER_PORTAL_API_B2C/1.0"
API_URL_B2B = "https://api.wstw.at/gateway/WN_SMART_METER_PORTAL_API_B2B/1.0"
REDIRECT_URI = "https://smartmeter-web.wienernetze.at/"
API_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
AUTH_URL = "https://log.wien/auth/realms/logwien/protocol/openid-connect/"

LOGIN_ARGS = {
    "client_id": "wn-smartmeter",
    "redirect_uri": REDIRECT_URI,
    "response_mode": "fragment",
    "response_type": "code",
    "scope": "openid",
    "nonce": "",
    "code_challenge": "",
    "code_challenge_method": "S256"
}

VALID_OBIS_CODES = {
    "1-1:1.8.0",
    "1-1:1.9.0",
    "1-1:2.8.0",
    "1-1:2.9.0"
}

class Resolution(enum.Enum):

    HOUR = "HOUR"
    QUARTER_HOUR = "QUARTER-HOUR"


class ValueType(enum.Enum):

    METER_READ = "METER_READ"
    DAY = "DAY"
    QUARTER_HOUR = "QUARTER_HOUR"

    @staticmethod
    def from_str(label):
        if label in ('METER_READ', 'meter_read'):
            return ValueType.METER_READ
        elif label in ('DAY', 'day'):
            return ValueType.DAY
        elif label in ('QUARTER_HOUR', 'quarter_hour'):
            return ValueType.QUARTER_HOUR
        else:
            raise NotImplementedError

class AnlagenType(enum.Enum):

    CONSUMING = "TAGSTROM"
    FEEDING = "BEZUG"

    @staticmethod
    def from_str(label):
        match label.upper():
            case 'TAGSTROM' | 'NACHTSTROM' | 'WAERMEPUMPE' | 'STROM' | 'WANDLER':
                return AnlagenType.CONSUMING
            case 'BEZUG':
                return AnlagenType.FEEDING
            case _:
                raise NotImplementedError(f"AnlageType {label} not implemented")

class RoleType(enum.Enum):

    DAILY_CONSUMING = "V001"
    QUARTER_HOURLY_CONSUMING = "V002"
    DAILY_FEEDING = "E001"
    QUARTER_HOURLY_FEEDING = "E002"

def build_access_token_args(**kwargs):

    args = {
        "grant_type": "authorization_code",
        "client_id": "wn-smartmeter",
        "redirect_uri": REDIRECT_URI
    }
    args.update(**kwargs)
    return args


def build_verbrauchs_args(**kwargs):

    args = {
        "period": "DAY",
        "accumulate": False,
        "offset": 0,
        "dayViewResolution": "HOUR",
    }
    args.update(**kwargs)
    return args
