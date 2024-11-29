import datetime as dt
import json
import os
import random
import sys
from datetime import datetime, timedelta
from importlib.resources import files
from urllib import parse
from urllib.parse import urlencode

import pytest
import requests
from requests_mock import Mocker

from test_resources import post_data_matcher

# necessary for pytest-cov to measure coverage
myPath = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, myPath + '/../../custom_components')
from wnsm import api  # noqa: E402
from wnsm.api.constants import ValueType, AnlagenType, RoleType  # noqa: E402


def _dt_string(datetime_string):
    return datetime_string.isoformat(timespec='milliseconds') + "Z"


PAGE_URL = "https://smartmeter-web.wienernetze.at/"
API_CONFIG_URL = "https://smartmeter-web.wienernetze.at/assets/app-config.json"
API_URL_ALT = "https://service.wienernetze.at/sm/api/"
API_URL_B2C = "https://api.wstw.at/gateway/WN_SMART_METER_PORTAL_API_B2C/1.0"
API_URL_B2B = "https://api.wstw.at/gateway/WN_SMART_METER_PORTAL_API_B2B/1.0"
REDIRECT_URI = "https://smartmeter-web.wienernetze.at/"
API_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
AUTH_URL = "https://log.wien/auth/realms/logwien/protocol/openid-connect"  # noqa
B2C_API_KEY = "afb0be74-6455-44f5-a34d-6994223020ba"
B2B_API_KEY = "93d5d520-7cc8-11eb-99bc-ba811041b5f6"
LOGIN_ARGS = {
    "client_id": "wn-smartmeter",
    "redirect_uri": REDIRECT_URI,
    "response_mode": "fragment",
    "response_type": "code",
    "scope": "openid",
    "nonce": "",
}

USERNAME = "margit.musterfrau@gmail.com"
PASSWORD = "Margit1234!"

RESPONSE_CODE = 'b04c44f7-55c6-4c0e-b2af-e9d9408ded2b.949e0f0d-b447-4208-bfef-273d694dc633.c514bbef-6269-48ca-9991-d7d5cd941213'  # noqa: E501

ACCESS_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBFbVQzTlI1UHV0TlVhelhaeVdlVXphcEhENzFuTW5BQVFZeU9PUWZYVk0ifQ.eyJleHAiOjE2NzczMTIxODEsImlhdCI6MTY3NzMxMTg4MSwiYXV0aF90aW1lIjoxNjc3MzExODgwLCJqdGkiOiIxMjM0NTY3OC0xMjM0LTEyMzQtMTIzNC0xMjM0NTY3ODkwMTIiLCJpc3MiOiJodHRwczovL2xvZy53aWVuL2F1dGgvcmVhbG1zL2xvZ3dpZW4iLCJhdWQiOiJhY2NvdW50Iiwic3ViIjoiMTIzNDU2NzgtMTIzNC0xMjM0LTEyMzQtMTIzNDU2Nzg5MDEyIiwidHlwIjoiQmVhcmVyIiwiYXpwIjoid24tc21hcnRtZXRlciIsIm5vbmNlIjoiMTIzNDU2NzgtMTIzNC0xMjM0LTEyMzQtMTIzNDU2Nzg5MDEyIiwic2Vzc2lvbl9zdGF0ZSI6IjEyMzQ1Njc4LTEyMzQtMTIzNC0xMjM0LTEyMzQ1Njc4OTAxMiIsImFsbG93ZWQtb3JpZ2lucyI6WyJodHRwczovL3NtYXJ0bWV0ZXItd2ViLndpZW5lcm5ldHplLmF0IiwiaHR0cHM6Ly93d3cud2llbmVybmV0emUuYXQiLCJodHRwOi8vbG9jYWxob3N0OjQyMDAiXSwicmVhbG1fYWNjZXNzIjp7InJvbGVzIjpbImRlZmF1bHQtcm9sZXMtd2xvZ2luIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYWNjb3VudCI6eyJyb2xlcyI6WyJtYW5hZ2UtYWNjb3VudCIsIm1hbmFnZS1hY2NvdW50LWxpbmtzIiwidmlldy1wcm9maWxlIl19fSwic2NvcGUiOiJvcGVuaWQgZW1haWwgcHJvZmlsZSIsInNpZCI6IjEyMzQ1Njc4LTEyMzQtMTIzNC0xMjM0LTEyMzQ1Njc4OTAxMiIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJuYW1lIjoiTWFyZ2l0IE11c3RlcmZyYXUiLCJjb21wYW55IjoiUHJpdmF0IiwicHJlZmVycmVkX3VzZXJuYW1lIjoibWFyZ2l0Lm11c3RlcmZyYXVAZ21haWwuY29tIiwic2FsdXRhdGlvbiI6IkZyYXUiLCJnaXZlbl9uYW1lIjoiTWFyZ2l0IiwibG9jYWxlIjoiZW4iLCJmYW1pbHlfbmFtZSI6Ik11c3RlcmZyYXUiLCJlbWFpbCI6Im1hcmdpdC5tdXN0ZXJmcmF1QGdtYWlsLmNvbSJ9.4x8uJ3LE8i5fnyw5qpTiZbi44hvoIM0MhQMCkmH_RUQ'  # noqa: E501
REFRESH_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImJkZDFhMDQ0LTgzZWUtNDUzMi1hOTk3LTBkMjI1YzcxNTYyNCJ9.eyJleHAiOjE2NzczMTM2ODEsImlhdCI6MTY3NzMxMTg4MSwianRpIjoiMTIzNDU2NzgtMTIzNC0xMjM0LTEyMzQtMTIzNDU2Nzg5MDEyIiwiaXNzIjoiaHR0cHM6Ly9sb2cud2llbi9hdXRoL3JlYWxtcy9sb2d3aWVuIiwiYXVkIjoiaHR0cHM6Ly9sb2cud2llbi9hdXRoL3JlYWxtcy9sb2d3aWVuIiwic3ViIjoiMTIzNDU2NzgtMTIzNC0xMjM0LTEyMzQtMTIzNDU2Nzg5MDEyIiwidHlwIjoiUmVmcmVzaCIsImF6cCI6InduLXNtYXJ0bWV0ZXIiLCJub25jZSI6IjEyMzQ1Njc4LTEyMzQtMTIzNC0xMjM0LTEyMzQ1Njc4OTAxMiIsInNlc3Npb25fc3RhdGUiOiIxMjM0NTY3OC0xMjM0LTEyMzQtMTIzNC0xMjM0NTY3ODkwMTIiLCJzY29wZSI6Im9wZW5pZCBlbWFpbCBwcm9maWxlIiwic2lkIjoiMTIzNDU2NzgtMTIzNC0xMjM0LTEyMzQtMTIzNDU2Nzg5MDEyIn0.eJ2f9hOGaLFgQmcL0WQDsyt3E92Ri9qmJ4lnhZY_W2o'  # noqa: E501
ID_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBFbVQzTlI1UHV0TlVhelhaeVdlVXphcEhENzFuTW5BQVFZeU9PUWZYVk0ifQ.eyJleHAiOjE2NzczMTIxODEsImlhdCI6MTY3NzMxMTg4MSwiYXV0aF90aW1lIjoxNjc3MzExODgwLCJqdGkiOiIxMjM0NTY3OC0xMjM0LTEyMzQtMTIzNC0xMjM0NTY3ODkwMTIiLCJpc3MiOiJodHRwczovL2xvZy53aWVuL2F1dGgvcmVhbG1zL2xvZ3dpZW4iLCJhdWQiOiJ3bi1zbWFydG1ldGVyIiwic3ViIjoiMTIzNDU2NzgtMTIzNC0xMjM0LTEyMzQtMTIzNDU2Nzg5MDEyIiwidHlwIjoiSUQiLCJhenAiOiJ3bi1zbWFydG1ldGVyIiwibm9uY2UiOiIxMjM0NTY3OC0xMjM0LTEyMzQtMTIzNC0xMjM0NTY3ODkwMTIiLCJzZXNzaW9uX3N0YXRlIjoiMTIzNDU2NzgtMTIzNC0xMjM0LTEyMzQtMTIzNDU2Nzg5MDEyIiwiYXRfaGFzaCI6ImZRQmFaQU1JVC1ucGktWmxCS1JTdHciLCJzaWQiOiIxMjM0NTY3OC0xMjM0LTEyMzQtMTIzNC0xMjM0NTY3ODkwMTIiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwibmFtZSI6Ik1hcmdpdCBNdXN0ZXJmcmF1IiwicHJlZmVycmVkX3VzZXJuYW1lIjoibWFyZ2l0Lm11c3RlcmZyYXVAZ21haWwuY29tIiwiZ2l2ZW5fbmFtZSI6Ik1hcmdpdCIsImxvY2FsZSI6ImVuIiwiZmFtaWx5X25hbWUiOiJNdXN0ZXJmcmF1IiwiZW1haWwiOiJtYXJnaXQubXVzdGVyZnJhdUBnbWFpbC5jb20ifQ.FBGAMU-bDKorGnIC-douEsKJ3VfwpNRBoeHMtytnow8'  # noqa: E501

zp_template = {
    "zaehlpunktnummer": "AT0010000000000000001000011111111",
    "equipmentNumber": "1111111111",
    "geraetNumber": "ABC1111111111111",
    "isSmartMeter": True,
    "isDefault": True,
    "isActive": True,
    "isDataDeleted": False,
    "isSmartMeterMarketReady": True,
    "dataDeletionTimestampUTC": None,
    "verbrauchsstelle": {
        "strasse": "Eine Strasse",
        "hausnummer": "1/2/3",
        "anlageHausnummer": "1",
        "postleitzahl": "1010",
        "ort": "Wien",
        "laengengrad": "16.3738",
        "breitengrad": "48.2082"
    },
    "anlage": {
        "typ": "TAGSTROM"
    },
    "vertraege": [
        {
            "einzugsdatum": "2010-01-01",
            "auszugsdatum": "2015-12-31"
        }
    ],
    "idexStatus": {
        "granularity": {
            "status": "QUARTER_HOUR",
            "canBeChanged": True
        },
        "customerInterface": {
            "status": "active",
            "canBeChanged": True
        },
        "display": {
            "isLocked": True,
            "canBeChanged": True
        },
        "displayProfile": {
            "canBeChanged": True,
            "displayProfile": "VERBRAUCH"
        }
    },
    "optOutDetails": {
        "isOptOut": False
    },
    "zpSharingInfo": {
        "isOwner": False
    }
}

zp_feeding_template = {
    "zaehlpunktnummer": "AT0010000000000000001000011111112",
    "equipmentNumber": "1111111111",
    "geraetNumber": "ABC1111111111111",
    "isSmartMeter": True,
    "isDefault": False,
    "isActive": True,
    "isDataDeleted": False,
    "isSmartMeterMarketReady": True,
    "dataDeletionTimestampUTC": None,
    "verbrauchsstelle": {
        "strasse": "Eine Strasse",
        "hausnummer": "1/2/3",
        "anlageHausnummer": "1",
        "postleitzahl": "1010",
        "ort": "Wien",
        "laengengrad": "16.3738",
        "breitengrad": "48.2082"
    },
    "anlage": {
        "typ": "BEZUG"
    },
    "vertraege": [
        {
            "einzugsdatum": "2010-01-01",
            "auszugsdatum": "2015-12-31"
        }
    ],
    "idexStatus": {
        "granularity": {
            "status": "QUARTER_HOUR",
            "canBeChanged": True
        },
        "customerInterface": {
            "status": "active",
            "canBeChanged": True
        },
        "display": {
            "isLocked": True,
            "canBeChanged": True
        },
        "displayProfile": {
            "canBeChanged": True,
            "displayProfile": "VERBRAUCH"
        }
    },
    "optOutDetails": {
        "isOptOut": False
    },
    "zpSharingInfo": {
        "isOwner": False
    }
}

def _set_status(zp: dict, status: bool):
    zp['isActive'] = status
    for idexStatus in ['granularity', 'customerInterface', 'display', 'displayProfile']:
        zp["idexStatus"][idexStatus]["canBeChanged"] = status
    return zp


def enabled(zp: dict):
    return _set_status(zp, True)


def disabled(zp: dict):
    return _set_status(zp, False)


def quarterly(zp: dict):
    zp["idexStatus"]["granularity"]["status"] = "QUARTER_HOUR"
    return zaehlpunkt


def hourly(zp: dict):
    zp["idexStatus"]["granularity"]["status"] = ""
    return zp


def zaehlpunkt():
    return dict(zp_template)

def zaehlpunkt_feeding():
    return dict(zp_feeding_template)

def zaehlpunkt_response(zps=None):
    return [
        {
            "bezeichnung": "Margit Musterfrau, Kundennummer 1234567890",
            "geschaeftspartner": "1234567890",
            "zaehlpunkte": zps or []
        }
    ]


def verbrauch_raw_response():
    return {
        "quarter-hour-opt-in": True,
        "values": [
            {
                "value": 5461,
                "timestamp": "2023-04-22T22:00:00.000Z",
                "isEstimated": False
            },
            {
                "value": 5513,
                "timestamp": "2023-04-23T22:00:00.000Z",
                "isEstimated": False
            },
            {
                "value": 4672,
                "timestamp": "2023-04-24T22:00:00.000Z",
                "isEstimated": False
            },
            {
                "value": 5550,
                "timestamp": "2023-04-25T22:00:00.000Z",
                "isEstimated": False
            },
            {
                "value": 3856,
                "timestamp": "2023-04-26T22:00:00.000Z",
                "isEstimated": False
            },
            {
                "value": 5137,
                "timestamp": "2023-04-27T22:00:00.000Z",
                "isEstimated": False
            },
            {
                "value": 6918,
                "timestamp": "2023-04-28T22:00:00.000Z",
                "isEstimated": False
            }
        ],
        "statistics": {
            "maximum": 6918,
            "minimum": 3856,
            "average": 5301
        }
    }
    
def history_response(
    zp: str,
    zaehlwerk_amount: int = 1,
    wrong_zp: bool = False,
    all_invalid_obis: bool = False,
    all_valid_obis: bool = False,
    empty_messwerte: bool = False,
    no_zaehlwerke: bool = False,
    empty_zaehlwerke: bool = False,
    no_obis_code: bool = False,
):
    """
    Generates test data for history response based on specified conditions.
    """
    valid_obis_codes = ["1-1:1.8.0", "1-1:1.9.0", "1-1:2.8.0", "1-1:2.9.0"]
    invalid_obis_code = "9-9:9.9.9"

    # Modify zp if wrong_zp is True
    if wrong_zp:
        zp = zp[:-1] + "9"

    # Handle no_zaehlwerke case
    if no_zaehlwerke:
        return {"zaehlpunkt": zp}

    # Handle empty zaehlwerke case
    if empty_zaehlwerke:
        return {"zaehlwerke": [], "zaehlpunkt": zp}

    # Prepare messwerte
    messwerte = [] if empty_messwerte else [
        {
            "messwert": 7256686,
            "zeitVon": "2024-11-11T23:00:00.000Z",
            "zeitBis": "2024-11-12T23:00:00.000Z",
            "qualitaet": "VAL",
        }
    ]

    # Generate zaehlwerke
    zaehlwerke = []
    for i in range(zaehlwerk_amount):
        if no_obis_code:
            zaehlwerke.append({"einheit": "WH", "messwerte": messwerte})
        else:
            if all_invalid_obis:
                obis = invalid_obis_code
            elif all_valid_obis or i == 0: # First one valid, or all valid if multiple_valid_obis is True
                obis = valid_obis_codes[i % len(valid_obis_codes)]
            else:  # Default: first valid, rest invalid
                obis = invalid_obis_code        
            zaehlwerke.append({"obisCode": obis, "einheit": "WH", "messwerte": messwerte})

    return {"zaehlwerke": zaehlwerke, "zaehlpunkt": zp}
    
def delta(i: str, n: int=0) -> timedelta:
    return {
        "h":  timedelta(hours=n),
        "d": timedelta(days=n),
        "qh": timedelta(minutes=15 * n)
    }[i.lower()]

def bewegungsdaten_value(ts: datetime, interval: str, i: int = 0) -> dict:
    t = ts.replace(minute=0, second=0, microsecond=0)
    return {
      "wert": round(random.gauss(0.045,0.015), 3),
      "zeitpunktVon": (t + delta(interval, i)).strftime('%Y-%m-%dT%H:%M:%SZ'),
      "zeitpunktBis": (t + delta(interval, i+1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
      "geschaetzt": False
    }

def bewegungsdaten(count=24, timestamp=None, interval='h'):
    if timestamp is None:
        timestamp = datetime.now().replace(minute=0, second=0, microsecond=0)
    return [bewegungsdaten_value(timestamp, interval, i) for i in list(range(0,count))]


def bewegungsdaten_response(customer_id: str, zp: str,
                            granularity: ValueType = ValueType.QUARTER_HOUR, anlagetype: AnlagenType = AnlagenType.CONSUMING,
                            wrong_zp: bool = False, values_count: int = 10):
    if (granularity == ValueType.QUARTER_HOUR):
        gran = "QH"
        if(anlagetype == AnlagenType.CONSUMING):
            rolle = "V002"
        else:
            rolle = "E002"
    else:
        gran = "D"
        if(anlagetype == AnlagenType.CONSUMING):
            rolle = "V001"
        else:
            rolle = "V002"
    if wrong_zp:
        zp = zp + "9"

    values = [] if values_count == 0 else bewegungsdaten(count=values_count, timestamp=datetime(2022,8,7,0,0,0), interval=gran)

    return {
        "descriptor": {
            "geschaeftspartnernummer": customer_id,
            "zaehlpunktnummer": zp,
            "rolle": rolle,
            "aggregat": "NONE",
            "granularitaet": gran,
            "einheit": "KWH"
        },
        "values": values
    }


def smartmeter(username=USERNAME, password=PASSWORD):
    return api.client.Smartmeter(username=username, password=password)


@pytest.mark.usefixtures("requests_mock")
def mock_login_page(requests_mock: Mocker, status: int | None = 200):
    """
    mock GET login url from login page (+ session_code + client_id + execution param)
    """
    get_login_url = AUTH_URL + "/auth?" + parse.urlencode(LOGIN_ARGS)
    if status == 200:
        requests_mock.get(url=get_login_url, text=files('test_resources').joinpath('auth.html').read_text())
    elif status is None:
        requests_mock.get(url=get_login_url, exc=requests.exceptions.ConnectTimeout)
    else:
        requests_mock.get(url=get_login_url, text='', status_code=status)


@pytest.mark.usefixtures("requests_mock")
def mock_get_api_key(requests_mock: Mocker, bearer_token: str = ACCESS_TOKEN,
                     get_config_status: int | None = 200, include_b2c_key: bool = True, include_b2b_key: bool = True,
                     same_b2c_url: bool = True, same_b2b_url: bool = True):
    """
    mock GET smartmeter-web.wienernetze.at to retrieve app-config.json which carries the b2cApiKey and b2bApiKey
    """
    config_path = files('test_resources').joinpath('app-config.json')
    config_response = config_path.read_text()
    
    config_data = json.loads(config_response)
    if not include_b2c_key:
        del config_data["b2cApiKey"]
    if not include_b2b_key:
        del config_data["b2bApiKey"]

    if not same_b2c_url:
        config_data["b2cApiUrl"] = "https://api.wstw.at/gateway/WN_SMART_METER_PORTAL_API_B2C/2.0"
    if not same_b2b_url:
        config_data["b2bApiUrl"] = "https://api.wstw.at/gateway/WN_SMART_METER_PORTAL_API_B2B/2.0"

    config_response = json.dumps(config_data)
        
    if get_config_status is None:
        requests_mock.get(url=API_CONFIG_URL, request_headers={"Authorization": f"Bearer {bearer_token}"},
                          exc=requests.exceptions.ConnectTimeout)        
    else:
        requests_mock.get(url=API_CONFIG_URL, request_headers={"Authorization": f"Bearer {bearer_token}"},
                          status_code=get_config_status, text=config_response)

@pytest.mark.usefixtures("requests_mock")
def mock_token(requests_mock: Mocker, code=RESPONSE_CODE, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN,
               id_token=ID_TOKEN, status: int | None = 200,
               expires: int = 300,
               token_type: str = "Bearer"):
    response = {
        "access_token": access_token,
        "expires_in": expires,
        "refresh_expires_in": 6 * expires,
        "refresh_token": refresh_token,
        "token_type": token_type,
        "id_token": id_token,
        "not-before-policy": 0,
        "session_state": "949e0f0d-b447-4208-bfef-273d694dc633",
        "scope": "openid email profile"
    }
    if status == 200:
        requests_mock.post(f'{AUTH_URL}/token', additional_matcher=post_data_matcher({
            "grant_type": "authorization_code",
            "client_id": "wn-smartmeter",
            "redirect_uri": REDIRECT_URI,
            "code": code
        }), json=response, status_code=status)
    elif status is None:
        requests_mock.post(f'{AUTH_URL}/token', additional_matcher=post_data_matcher({
            "grant_type": "authorization_code",
            "client_id": "wn-smartmeter",
            "redirect_uri": REDIRECT_URI,
            "code": code
        }), exc=requests.exceptions.ConnectTimeout)
    else:
        requests_mock.post(f'{AUTH_URL}/token', additional_matcher=post_data_matcher({
            "grant_type": "authorization_code",
            "client_id": "wn-smartmeter",
            "redirect_uri": REDIRECT_URI,
            "code": code
        }), json={}, status_code=status)


@pytest.mark.usefixtures("requests_mock")
def mock_authenticate(requests_mock: Mocker, username, password, code=RESPONSE_CODE, status: int | None = 302):
    """
    mock POST authenticate call resulting in a 302 Found redirecting to another Location
    """
    authenticate_query_params = {
        "session_code": "SESSION_CODE_PLACEHOLDER",
        "execution": "5939ddcc-efd4-407c-b01c-df8977d522b5",
        "client_id": "wn-smartmeter",
        "tab_id": "6tDgFA2FxbU"
    }
    authenticate_url = f'https://log.wien/auth/realms/logwien/login-actions/authenticate?{parse.urlencode(authenticate_query_params)}'

    # for some weird reason we have to perform this call before. maybe to create a login session. idk
    requests_mock.post(authenticate_url, status_code=status,
                       additional_matcher=post_data_matcher({"username": username, "login": " "}),
                       text=files('test_resources').joinpath('auth.html').read_text()
                       )

    if status == 302:
        redirect_url = f'{REDIRECT_URI}/#state=cb142d1b-d8b4-4bf3-8a3e-92544790c5c4' \
                       '&session_state=949e0f0d-b447-4208-bfef-273d694dc633' \
                       f'&code={code}'
        requests_mock.post(authenticate_url, status_code=status,
                           additional_matcher=post_data_matcher({"username": username, "password": password}),
                           headers={'location': redirect_url},
                           )
        requests_mock.get(redirect_url, text='Some page which loads a js, performing a call to /token')
    elif status == 403:  # do not provide Location header on 403
        requests_mock.post(authenticate_url, status_code=status,
                           additional_matcher=post_data_matcher({"username": username, "password": password})
                           )
    elif status == 404:  # do provide a redirect to not-found page in Location header on 404 -> 302
        requests_mock.post(authenticate_url, status_code=302,
                           additional_matcher=post_data_matcher({"username": username, "password": password}),
                           headers={'location': REDIRECT_URI + "not-found"}
                           )
    elif status == 201:  # if code is not within query params, but encoded otherwise
        redirect_url = f'{REDIRECT_URI}/#code={code}#state=cb142d1b-d8b4-4bf3-8a3e-92544790c5c4' \
                       '&session_state=949e0f0d-b447-4208-bfef-273d694dc633'
        requests_mock.post(authenticate_url, status_code=201,
                           additional_matcher=post_data_matcher({"username": username, "password": password}),
                           headers={'location': redirect_url}
                           )
    elif status is None:
        requests_mock.post(authenticate_url, exc=requests.exceptions.ConnectTimeout,
                           additional_matcher=post_data_matcher({"username": username, "password": password})
                           )


@pytest.mark.usefixtures("requests_mock")
def expect_login(requests_mock: Mocker, username=USERNAME, password=PASSWORD):
    mock_login_page(requests_mock)
    mock_authenticate(requests_mock, username, password)
    mock_token(requests_mock)
    mock_get_api_key(requests_mock)


@pytest.mark.usefixtures("requests_mock")
def expect_zaehlpunkte(requests_mock: Mocker, zps: list[dict]):
    requests_mock.get(parse.urljoin(API_URL_B2C,'zaehlpunkte'),
                      headers={
                          "Authorization": f"Bearer {ACCESS_TOKEN}",
                          "X-Gateway-APIKey": B2C_API_KEY,
                      },
                      json=zaehlpunkt_response(zps))


@pytest.mark.usefixtures("requests_mock")
def expect_verbrauch(requests_mock: Mocker, customer_id: str, zp: str, dateFrom: dt.datetime, response: dict,
                     granularity='DAY', resolution='HOUR'):
    params = {
        "dateFrom": _dt_string(dateFrom),
        "dayViewResolution": resolution
    }
    path = f'messdaten/{customer_id}/{zp}/verbrauch?{urlencode(params)}'
    requests_mock.get(parse.urljoin(API_URL_B2C,path),
                      headers={
                          "Authorization": f"Bearer {ACCESS_TOKEN}",
                          "X-Gateway-APIKey": B2C_API_KEY,
                      },
                      json=response)


@pytest.mark.usefixtures("requests_mock")
def expect_history(
    requests_mock: Mocker, 
    customer_id: str, 
    zp: str,
    zaehlwerk_amount: int = 1,
    wrong_zp: bool = False,
    all_invalid_obis: bool = False,
    all_valid_obis: bool = False,
    empty_messwerte: bool = False,
    no_zaehlwerke: bool = False,
    empty_zaehlwerke: bool = False,
    no_obis_code: bool = False
):
    path = f'zaehlpunkte/{customer_id}/{zp}/messwerte'
    requests_mock.get(parse.urljoin(API_URL_B2B, path),
                      headers={
                          "Authorization": f"Bearer {ACCESS_TOKEN}",
                          "X-Gateway-APIKey": B2B_API_KEY,
                          "Accept": "application/json"
                      },
                      json=history_response(
                          zp, 
                          zaehlwerk_amount, 
                          wrong_zp, 
                          all_invalid_obis, 
                          all_valid_obis, 
                          empty_messwerte, 
                          no_zaehlwerke, 
                          empty_zaehlwerke,
                          no_obis_code
                        )
                      )

@pytest.mark.usefixtures("requests_mock")
def expect_bewegungsdaten(requests_mock: Mocker, customer_id: str, zp: str, dateFrom: dt.datetime, dateTo: dt.datetime,
                          granularity:ValueType = ValueType.QUARTER_HOUR, anlagetype: AnlagenType = AnlagenType.CONSUMING,
                          wrong_zp: bool = False, values_count=10):
    if anlagetype== AnlagenType.FEEDING:
        if granularity == ValueType.DAY: 
            rolle = RoleType.DAILY_FEEDING.value 
        else:
            rolle = RoleType.QUARTER_HOURLY_FEEDING.value 
    else: 
        if granularity == ValueType.DAY: 
            rolle = RoleType.DAILY_CONSUMING.value 
        else: 
            rolle = RoleType.QUARTER_HOURLY_CONSUMING.value
    params = {
        "geschaeftspartner": customer_id,
        "zaehlpunktnummer": zp,
        "rolle": rolle,
        "zeitpunktVon": dateFrom.strftime("%Y-%m-%dT00:00:00.000Z"),
        "zeitpunktBis": dateTo.strftime("%Y-%m-%dT23:59:59.999Z"),
        "aggregat": "NONE"
    }
    url = parse.urljoin(API_URL_ALT, f'user/messwerte/bewegungsdaten?{urlencode(params)}')
    requests_mock.get(url,
                      headers={
                          "Authorization": f"Bearer {ACCESS_TOKEN}",
                          "Accept": "application/json"
                      },
                      json=bewegungsdaten_response(customer_id, zp, granularity, anlagetype, wrong_zp, values_count))
