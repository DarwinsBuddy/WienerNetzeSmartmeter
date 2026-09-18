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
    "code_challenge": "",
    "code_challenge_method": "S256"
}

VALID_OBIS_CODES = {
    "1-1:1.8.0", #: Total Meter reading of consumption in Wh on selected day(s)- updated daily - used by Wiener Netze as default for meter reading ("Zählerstand")
    "1-1:1.9.0", #: Measured value of consumption in Wh in quarter hour or daily steps - updated daily - also used by Wiener Netze for meter readings of heat pumps
    "1-1:2.8.0", #: Total Meter reading of production/feeding on selected day(s) in Wh - used by Wiener Netze as default for meter reading ("Zählerstand")
    "1-1:2.9.0" #: Measured value of production/feeding in Wh in quarter hour or daily steps - updated daily - currently unused by Wiener Netze but accesible via API (call to zaehlpunkte/{customer_id}/{zaehlpunkt}/messwerte with ValueType DAY or QUARTER_HOUR)
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

class AnlagenType(enum.Enum):
    """Possible types for the zaehlpunkte"""
    CONSUMING = "TAGSTROM"  #: Zaehlpunkt is consuming ("normal" power connection)
    FEEDING = "BEZUG"  #: Zaehlpunkt is feeding (produced power from PV, etc.)
    
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
        "redirect_uri": REDIRECT_URI
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


# ---------------------------------------------------------------------------
# Official Wiener Netze Smart Meter API (WN_SMART_METER_API)
# ---------------------------------------------------------------------------
# This is the public, OAuth2-secured API that Wiener Netze documents at
# https://api-portal.wienerstadtwerke.at. Unlike the "portal" endpoints above,
# it does not require any HTML scraping: authentication is a standard
# OAuth2 client_credentials exchange and requests carry both a Bearer access
# token and the per-application x-Gateway-APIKey header.

OFFICIAL_API_URL: str = "https://api.wstw.at/gateway/WN_SMART_METER_API/1.0"
OFFICIAL_TOKEN_URL: str = (
    "https://api.wstw.at/invoke/pub.apigateway.oauth2/getAccessToken"
)
OFFICIAL_AUTHORIZE_URL: str = (
    "https://api.wstw.at/invoke/pub.apigateway.oauth2/authorize"
)
OFFICIAL_DEFAULT_SCOPE: str = "profile"
# Wiener Netze issues tokens valid for this many seconds; refresh a little
# earlier so concurrent calls never race a just-expired token.
OFFICIAL_TOKEN_VALIDITY_SECONDS: int = 3600
OFFICIAL_TOKEN_REFRESH_LEEWAY_SECONDS: int = 60
# Date format expected by /zaehlpunkte/messwerte (ISO 8601 date, no time).
OFFICIAL_API_DATE_FORMAT: str = "%Y-%m-%d"


class Wertetyp(enum.Enum):
    """Valid ``wertetyp`` query parameter values for the official API.

    These match what the Wiener Netze gateway accepts on
    ``GET /zaehlpunkte/messwerte`` and ``GET /zaehlpunkte/{zp}/messwerte``.
    """

    QUARTER_HOUR = "QUARTER_HOUR"  #: 15-minute interval values
    DAY = "DAY"  #: Daily aggregated values
    METER_READ = "METER_READ"  #: Meter readings ("Zählerstand")

    @staticmethod
    def from_str(label: str) -> "Wertetyp":
        normalised = label.strip().upper()
        for member in Wertetyp:
            if member.value == normalised:
                return member
        raise ValueError(f"Unknown Wertetyp: {label!r}")
