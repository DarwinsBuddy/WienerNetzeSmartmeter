"""
API constants used by the Wiener-Netze Smartmeter client.
"""

import enum

PAGE_URL = "https://smartmeter-web.wienernetze.at/"
API_CONFIG_URL = "https://smartmeter-web.wienernetze.at/assets/app-config.json"
API_URL_ALT = "https://service.wienernetze.at/sm/api/"

# These two URLs are also published by the frontend as ``b2cApiUrl`` and
# ``b2bApiUrl`` and may change over time.
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
    # Total meter reading of consumption in Wh on selected day(s) - updated
    # daily and used by Wiener Netze as the default Zaehlerstand.
    "1-1:1.8.0",
    # Measured consumption in Wh in quarter-hour or daily steps - also used by
    # Wiener Netze for some heat-pump style meter readings.
    "1-1:1.9.0",
    # Total production/feeding meter reading in Wh.
    "1-1:2.8.0",
    # Measured production/feeding in Wh in quarter-hour or daily steps.
    "1-1:2.9.0"
}

class Resolution(enum.Enum):
    """Possible resolution for one-day consumption data."""

    HOUR = "HOUR"
    QUARTER_HOUR = "QUARTER-HOUR"


class ValueType(enum.Enum):
    """Possible ``wertetyp`` values for historical-data queries."""

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
    """Possible installation types returned for a metering point."""

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
    """Original role types used by the classic movement-data endpoint."""

    DAILY_CONSUMING = "V001"
    QUARTER_HOURLY_CONSUMING = "V002"
    DAILY_FEEDING = "E001"
    QUARTER_HOURLY_FEEDING = "E002"

def build_access_token_args(**kwargs):
    """Build access-token arguments and merge custom keyword arguments."""

    args = {
        "grant_type": "authorization_code",
        "client_id": "wn-smartmeter",
        "redirect_uri": REDIRECT_URI
    }
    args.update(**kwargs)
    return args


def build_verbrauchs_args(**kwargs):
    """Build arguments for the legacy consumption endpoint."""

    args = {
        "period": "DAY",
        # Can be changed to True to get a cumulative sum.
        "accumulate": False,
        # Additional offset to start the cumulative sum with.
        "offset": 0,
        "dayViewResolution": "HOUR",
    }
    args.update(**kwargs)
    return args
