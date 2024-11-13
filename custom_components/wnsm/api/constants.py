"""
    api constants
"""
import enum

PAGE_URL = "https://smartmeter-web.wienernetze.at/"
API_CONFIG_URL = "https://smartmeter-web.wienernetze.at/assets/app-config.json"
API_URL_ALT = "https://service.wienernetze.at/sm/api/"
# These two URLS are also coded in the js as b2cApiUrl and b2bApiUrl
API_URL = "https://api.wstw.at/gateway/WN_SMART_METER_PORTAL_API_B2C/1.0"
API_URL_B2B = "https://api.wstw.at/gateway/WN_SMART_METER_PORTAL_API_B2B/1.0"
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

VALID_OBIS_CODES = {
    "1-1:1.8.0", #: Sum of consumption in kWh - used by Wiener Netze as default
    "1-1:1.9.0", #: Sum of consumption in kWh - used by Wiener Netze for heat pumps - per standard this should be the default
    "1-1:2.8.0", #: Sum of production in kWh - used by Wiener Netzte as default
    "1-1:2.9.0" #: Sum of production in kWh - currently unused - per standard this should be the default
}

class Resolution(enum.Enum):
    """Possible resolution for consumption data of one day"""
    HOUR = "HOUR"  #: gets consumption data per hour
    QUARTER_HOUR = "QUARTER-HOUR"  #: gets consumption data per 15min


class ValueType(enum.Enum):
    """Possible 'wertetyp' for querying historical data"""
    METER_READ = "METER_READ"  #: Meter reading for the day
    DAY = "DAY"  #: Consumption for the day
    QUARTER_HOUR = "QUARTER_HOUR"  #: Consumption for 15min slots

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

class AnlageType(enum.Enum):
    """Possible types for the zaehlpunkte"""
    CONSUMING = "TAGSTROM"  #: Zaehlpunkt is consuming ("normal" power connection)
    FEEDING = "BEZUG"  #: Zaehlpunkt is feeding (produced power from PV, etc.)
    
    @staticmethod
    def from_str(label):
        if label in ('TAGSTROM', 'tagstrom'):
            return AnlageType.CONSUMING
        elif label in ('WAERMEPUMPE', 'waermepumpe'):
            return AnlageType.CONSUMING
        elif label in ('STROM', 'strom'):
            return AnlageType.CONSUMING
        elif label in ('BEZUG', 'bezug'):
            return AnlageType.FEEDING
        else:
            raise NotImplementedError
            
class RoleType(enum.Enum):
    """Possible types for the roles of bewegungsdaten - depending on the settings set in smart meter portal"""
    DAILY_CONSUMING = "V001"  #: Consuming data is updated in daily steps
    QUARTER_HOURLY_CONSUMING = "V002"  #: Consuming data is updated in quarter hour steps
    DAILY_FEEDING = "E001"  #: Feeding data is updated in daily steps
    QUARTER_HOURLY_FEEDING = "E002"  #: Feeding data is updated in quarter hour steps

def build_access_token_args(**kwargs):
    """
    build access token and add kwargs
    """
    args = {
        "grant_type": "authorization_code",
        "client_id": "wn-smartmeter",
        "redirect_uri": REDIRECT_URI,
    }
    args.update(**kwargs)
    return args


def build_verbrauchs_args(**kwargs):
    """
    build arguments for verbrauchs call and add kwargs
    """
    args = {
        "period": "DAY",
        "accumulate": False,  # can be changed to True to get a cum-sum
        "offset": 0,  # additional offset to start cum-sum with
        "dayViewResolution": "HOUR",
    }
    args.update(**kwargs)
    return args
