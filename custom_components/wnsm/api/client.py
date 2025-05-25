"""Contains the Smartmeter API Client."""
import json
import logging
from datetime import datetime, timedelta, date
from urllib import parse
from typing import List, Dict, Any

import requests
from dateutil.relativedelta import relativedelta
from lxml import html

import base64
import hashlib
import os
import copy

from . import constants as const
from .errors import (
    SmartmeterConnectionError,
    SmartmeterLoginError,
    SmartmeterQueryError,
)

logger = logging.getLogger(__name__)


class Smartmeter:
    """Smartmeter client."""

    def __init__(self, username, password):
        """Access the Smartmeter API.

        Args:
            username (str): Username used for API Login.
            password (str): Password used for API Login.
        """
        self.username = username
        self.password = password
        self.session = requests.Session()
        self._access_token = None
        self._refresh_token = None
        self._api_gateway_token = None
        self._access_token_expiration = None
        self._refresh_token_expiration = None
        self._api_gateway_b2b_token = None
        self._code_verifier = None
        self._code_challenge = None
        self._local_login_args = None

    def reset(self):
        self.session = requests.Session()
        self._access_token = None
        self._refresh_token = None
        self._api_gateway_token = None
        self._access_token_expiration = None
        self._refresh_token_expiration = None
        self._api_gateway_b2b_token = None
        self._code_verifier = None
        self._code_challenge = None
        self._local_login_args = None

    def is_login_expired(self):
        return self._access_token_expiration is not None and datetime.now() >= self._access_token_expiration

    def is_logged_in(self):
        return self._access_token is not None and not self.is_login_expired()

    def generate_code_verifier(self):
        """
        generate a code verifier
        """
        return base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')
    
    def generate_code_challenge(self, code_verifier):
        """
        generate a code challenge from the code verifier
        """
        code_challenge = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        return base64.urlsafe_b64encode(code_challenge).decode('utf-8').rstrip('=')

    def load_login_page(self):
        """
        loads login page and extracts encoded login url
        """
        
        #generate a code verifier, which serves as a secure random value
        if not hasattr(self, '_code_verifier') or self._code_verifier is None:
           #only generate if it does not exist 
           self._code_verifier = self.generate_code_verifier()
        
        #generate a code challenge from the code verifier to enhance security
        self._code_challenge = self.generate_code_challenge(self._code_verifier)
        
        #copy const.LOGIN_ARGS
        self._local_login_args = copy.deepcopy(const.LOGIN_ARGS)
        
        #add code_challenge in self._local_login_args
        self._local_login_args["code_challenge"] = self._code_challenge
        
        login_url = const.AUTH_URL + "auth?" + parse.urlencode(self._local_login_args)
        try:
            result = self.session.get(login_url)
        except Exception as exception:
            raise SmartmeterConnectionError("Could not load login page") from exception
        if result.status_code != 200:
            raise SmartmeterConnectionError(
                f"Could not load login page. Error: {result.content}"
            )
        tree = html.fromstring(result.content)
        forms = tree.xpath("(//form/@action)")
        
        if not forms:
            raise SmartmeterConnectionError("No form found on the login page.")
        
        action = forms[0]
        return action

    def credentials_login(self, url):
        """
        login with credentials provided the login url
        """
        try:
            result = self.session.post(
                url,
                data={
                    "username": self.username,
                    "login": " "
                },
                allow_redirects=False,
            )
            tree = html.fromstring(result.content)
            action = tree.xpath("(//form/@action)")[0]

            result = self.session.post(
                action,
                data={
                    "username": self.username,
                    "password": self.password,
                },
                allow_redirects=False,
            )
        except Exception as exception:
            raise SmartmeterConnectionError(
                "Could not login with credentials"
            ) from exception

        if "Location" not in result.headers:
            raise SmartmeterLoginError("Login failed. Check username/password.")
        location = result.headers["Location"]

        parsed_url = parse.urlparse(location)

        fragment_dict = dict(
            [
                x.split("=")
                for x in parsed_url.fragment.split("&")
                if len(x.split("=")) == 2
            ]
        )
        if "code" not in fragment_dict:
            raise SmartmeterLoginError(
                "Login failed. Could not extract 'code' from 'Location'"
            )

        code = fragment_dict["code"]
        return code

    def load_tokens(self, code):
        """
        Provided the totp code loads access and refresh token
        """
        try:
            result = self.session.post(
                const.AUTH_URL + "token",
                data=const.build_access_token_args(code=code , code_verifier=self._code_verifier)
            )
        except Exception as exception:
            raise SmartmeterConnectionError(
                "Could not obtain access token"
            ) from exception

        if result.status_code != 200:
            raise SmartmeterConnectionError(
                f"Could not obtain access token: {result.content}"
            )
        tokens = result.json()
        if tokens["token_type"] != "Bearer":
            raise SmartmeterLoginError(
                f'Bearer token required, but got {tokens["token_type"]!r}'
            )
        return tokens

    def login(self):
        """
        login with credentials specified in ctor
        """
        if self.is_login_expired():
            self.reset()
        if not self.is_logged_in():
            url = self.load_login_page()
            code = self.credentials_login(url)
            tokens = self.load_tokens(code)
            self._access_token = tokens["access_token"]
            self._refresh_token = tokens["refresh_token"]
            now = datetime.now()
            self._access_token_expiration = now + timedelta(seconds=tokens["expires_in"])
            self._refresh_token_expiration = now + timedelta(
                seconds=tokens["refresh_expires_in"]
            )

            logger.debug("Access Token valid until %s" % self._access_token_expiration)

            self._api_gateway_token, self._api_gateway_b2b_token = self._get_api_key(
                self._access_token
            )
        return self

    def _access_valid_or_raise(self):
        """Checks if the access token is still valid or raises an exception"""
        if datetime.now() >= self._access_token_expiration:
            # TODO: If the refresh token is still valid, it could be refreshed here
            raise SmartmeterConnectionError(
                "Access Token is not valid anymore, please re-log!"
            )

    def _get_api_key(self, token):
        self._access_valid_or_raise()

        headers = {"Authorization": f"Bearer {token}"}
        try:
            result = self.session.get(const.API_CONFIG_URL, headers=headers).json()
        except Exception as exception:
            raise SmartmeterConnectionError("Could not obtain API key") from exception

        find_keys = ["b2cApiKey", "b2bApiKey"]
        for key in find_keys:
            if key not in result:
                raise SmartmeterConnectionError(f"{key} not found in response!")

        # The b2bApiUrl and b2cApiUrl can also be gathered from the configuration
        # TODO: reduce code duplication...
        if "b2cApiUrl" in result and result["b2cApiUrl"] != const.API_URL:
            const.API_URL = result["b2cApiUrl"]
            logger.warning("The b2cApiUrl has changed to %s! Update API_URL!", const.API_URL)
        if "b2bApiUrl" in result and result["b2bApiUrl"] != const.API_URL_B2B:
            const.API_URL_B2B = result["b2bApiUrl"]
            logger.warning("The b2bApiUrl has changed to %s! Update API_URL_B2B!", const.API_URL_B2B)

        return (result[key] for key in find_keys)

    @staticmethod
    def _dt_string(datetime_string):
        return datetime_string.strftime(const.API_DATE_FORMAT)[:-3] + "Z"

    def _call_api(
        self,
        endpoint,
        base_url=None,
        method="GET",
        data=None,
        query=None,
        return_response=False,
        timeout=60.0,
        extra_headers=None,
    ):
        self._access_valid_or_raise()

        if base_url is None:
            base_url = const.API_URL
        url = parse.urljoin(base_url, endpoint)

        if query:
            url += ("?" if "?" not in endpoint else "&") + parse.urlencode(query)

        headers = {
            "Authorization": f"Bearer {self._access_token}",
        }

        # For API calls to B2C or B2B, we need to add the Gateway-APIKey:
        # TODO: This may be prone to errors if URLs are compared like this.
        #       The Strings has to be exactly the same, but that may not be the case,
        #       even though the URLs are the same.
        if base_url == const.API_URL:
            headers["X-Gateway-APIKey"] = self._api_gateway_token
        elif base_url == const.API_URL_B2B:
            headers["X-Gateway-APIKey"] = self._api_gateway_b2b_token

        if extra_headers:
            headers.update(extra_headers)

        if data:
            headers["Content-Type"] = "application/json"

        response = self.session.request(
            method, url, headers=headers, json=data, timeout=timeout
        )

        logger.debug("\nAPI Request: %s\n%s\n\nAPI Response: %s" % (
            url, ("" if data is None else "body: "+json.dumps(data, indent=2)),
            None if response is None or response.json() is None else json.dumps(response.json(), indent=2)))

        if return_response:
            return response

        return response.json()

    def get_zaehlpunkt(self, zaehlpunkt: str = None) -> tuple[str, str, str]:
        contracts = self.zaehlpunkte()
        if zaehlpunkt is None:
            customer_id = contracts[0]["geschaeftspartner"]
            zp = contracts[0]["zaehlpunkte"][0]["zaehlpunktnummer"]
            anlagetype = contracts[0]["zaehlpunkte"][0]["anlage"]["typ"]
        else:
            customer_id = zp = anlagetype = None
            for contract in contracts:
                zp_details = [z for z in contract["zaehlpunkte"] if z["zaehlpunktnummer"] == zaehlpunkt]
                if len(zp_details) > 0:
                    anlagetype = zp_details[0]["anlage"]["typ"]
                    zp = zp_details[0]["zaehlpunktnummer"]
                    customer_id = contract["geschaeftspartner"]
        return customer_id, zp, const.AnlagenType.from_str(anlagetype)

    def zaehlpunkte(self):
        """Returns zaehlpunkte for currently logged in user."""
        return self._call_api("zaehlpunkte")

    def consumptions(self):
        """Returns response from 'consumptions' endpoint."""
        return self._call_api("zaehlpunkt/consumptions")

    def base_information(self):
        """Returns response from 'baseInformation' endpoint."""
        return self._call_api("zaehlpunkt/baseInformation")

    def meter_readings(self):
        """Returns response from 'meterReadings' endpoint."""
        return self._call_api("zaehlpunkt/meterReadings")

    def verbrauch(
        self,
        customer_id: str,
        zaehlpunkt: str,
        date_from: datetime,
        resolution: const.Resolution = const.Resolution.HOUR
    ):
        """Returns energy usage.

        This returns hourly or quarter hour consumptions for a single day,
        i.e., for 24 hours after the given date_from.

        Args:
            customer_id (str): Customer ID returned by zaehlpunkt call ("geschaeftspartner")
            zaehlpunkt (str, optional): id for desired smartmeter.
                If None, check for first meter in user profile.
            date_from (datetime): Start date for energy usage request
            date_to (datetime, optional): End date for energy usage request.
                Defaults to datetime.now()
            resolution (const.Resolution, optional): Specify either 1h or 15min resolution
        Returns:
            dict: JSON response of api call to
                'messdaten/CUSTOMER_ID/ZAEHLPUNKT/verbrauchRaw'
        """
        if zaehlpunkt is None or customer_id is None:
            customer_id, zaehlpunkt, anlagetype = self.get_zaehlpunkt()
        endpoint = f"messdaten/{customer_id}/{zaehlpunkt}/verbrauch"
        query = const.build_verbrauchs_args(
            # This one does not have a dateTo...
            dateFrom=self._dt_string(date_from),
            dayViewResolution=resolution.value
        )
        return self._call_api(endpoint, query=query)

    def verbrauchRaw(
        self,
        customer_id: str,
        zaehlpunkt: str,
        date_from: datetime,
        date_to: datetime = None,
    ):
        """Returns energy usage.
        This can be used to query the daily consumption for a long period of time,
        for example several months or a week.

        Note: The minimal resolution is a single day.
        For hourly consumptions use `verbrauch`.

        Args:
            customer_id (str): Customer ID returned by zaehlpunkt call ("geschaeftspartner")
            zaehlpunkt (str, optional): id for desired smartmeter.
                If None, check for first meter in user profile.
            date_from (datetime): Start date for energy usage request
            date_to (datetime, optional): End date for energy usage request.
                Defaults to datetime.now()
        Returns:
            dict: JSON response of api call to
                'messdaten/CUSTOMER_ID/ZAEHLPUNKT/verbrauchRaw'
        """
        if date_to is None:
            date_to = datetime.now()
        if zaehlpunkt is None or customer_id is None:
            customer_id, zaehlpunkt, anlagetype = self.get_zaehlpunkt()
        endpoint = f"messdaten/{customer_id}/{zaehlpunkt}/verbrauchRaw"
        query = dict(
            # These are the only three fields that are used for that endpoint:
            dateFrom=self._dt_string(date_from),
            dateTo=self._dt_string(date_to),
            granularity="DAY",
        )
        return self._call_api(endpoint, query=query)

    def profil(self):
        """Returns profile of a logged-in user.

        Returns:
            dict: JSON response of api call to 'user/profile'
        """
        return self._call_api("user/profile", const.API_URL_ALT)

    def ereignisse(
        self, date_from: datetime, date_to: datetime = None, zaehlpunkt=None
    ):
        """Returns events between date_from and date_to of a specific smart meter.
        Args:
            date_from (datetime.datetime): Starting date for request
            date_to (datetime.datetime, optional): Ending date for request.
                Defaults to datetime.datetime.now().
            zaehlpunkt (str, optional): id for desired smart meter.
                If is None check for first meter in user profile.
        Returns:
            dict: JSON response of api call to 'user/ereignisse'
        """
        if date_to is None:
            date_to = datetime.now()
        if zaehlpunkt is None:
            customer_id, zaehlpunkt, anlagetype = self.get_zaehlpunkt()
        query = {
            "zaehlpunkt": zaehlpunkt,
            "dateFrom": self._dt_string(date_from),
            "dateUntil": self._dt_string(date_to),
        }
        return self._call_api("user/ereignisse", const.API_URL_ALT, query=query)

    def create_ereignis(self, zaehlpunkt, name, date_from, date_to=None):
        """Creates new event.
        Args:
            zaehlpunkt (str): Id for desired smartmeter.
                If None, check for first meter in user profile
            name (str): Event name
            date_from (datetime.datetime): (Starting) date for request
            date_to (datetime.datetime, optional): Ending date for request.
        Returns:
            dict: JSON response of api call to 'user/ereignis'
        """
        if date_to is None:
            dto = None
            typ = "ZEITPUNKT"
        else:
            dto = self._dt_string(date_to)
            typ = "ZEITSPANNE"

        data = {
            "endAt": dto,
            "name": name,
            "startAt": self._dt_string(date_from),
            "typ": typ,
            "zaehlpunkt": zaehlpunkt,
        }

        return self._call_api("user/ereignis", data=data, method="POST")

    def delete_ereignis(self, ereignis_id):
        """Deletes ereignis."""
        return self._call_api(f"user/ereignis/{ereignis_id}", method="DELETE")

    def find_valid_obis_data(self, zaehlwerke: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Find and validate data with valid OBIS codes from a list of zaehlwerke.
        """
        
        # Check if any OBIS codes exist
        all_obis_codes = [zaehlwerk.get("obisCode") for zaehlwerk in zaehlwerke]
        if not any(all_obis_codes):
            logger.debug("Returned zaehlwerke: %s", zaehlwerke)
            raise SmartmeterQueryError("No OBIS codes found in the provided data.")
        
        # Filter data for valid OBIS codes
        valid_data = [
            zaehlwerk for zaehlwerk in zaehlwerke
            if zaehlwerk.get("obisCode") in const.VALID_OBIS_CODES
        ]
        
        if not valid_data:
            logger.debug("Returned zaehlwerke: %s", zaehlwerke)
            raise SmartmeterQueryError(f"No valid OBIS code found. OBIS codes in data: {all_obis_codes}")
        
        # Check for empty or missing messwerte
        for zaehlwerk in valid_data:
            if not zaehlwerk.get("messwerte"):
                obis = zaehlwerk.get("obisCode")
                logger.debug(f"Valid OBIS code '{obis}' has empty or missing messwerte. Data is probably not available yet.")
                
        # Log a warning if multiple valid OBIS codes are found        
        if len(valid_data) > 1:
            found_valid_obis = [zaehlwerk["obisCode"] for zaehlwerk in valid_data]
            logger.warning(f"Multiple valid OBIS codes found: {found_valid_obis}. Using the first one.")

        return valid_data[0]

    def historical_data(
        self,
        zaehlpunktnummer: str = None,
        date_from: date = None,
        date_until: date = None,
        valuetype: const.ValueType = const.ValueType.METER_READ
    ):
        """
        Query historical data in a batch
        If no arguments are given, a span of three year is queried (same day as today but from current year - 3).
        If date_from is not given but date_until, again a three year span is assumed.
        """
        # Resolve Zaehlpunkt
        if zaehlpunktnummer is None:
            customer_id, zaehlpunkt, anlagetype = self.get_zaehlpunkt()
        else:
            customer_id, zaehlpunkt, anlagetype = self.get_zaehlpunkt(zaehlpunktnummer)

        # Set date range defaults
        if date_until is None:
            date_until = date.today()
            
        if date_from is None:
            date_from = date_until - relativedelta(years=3)

        # Query parameters
        query = {
            "datumVon": date_from.strftime("%Y-%m-%d"),
            "datumBis": date_until.strftime("%Y-%m-%d"),
            "wertetyp": valuetype.value,
        }
        
        extra = {
            # For this API Call, requesting json is important!
            "Accept": "application/json"
        }

        # API Call
        data = self._call_api(
            f"zaehlpunkte/{customer_id}/{zaehlpunkt}/messwerte",
            base_url=const.API_URL_B2B,
            query=query,
            extra_headers=extra,
        )

        # Sanity check: Validate returned zaehlpunkt
        if data.get("zaehlpunkt") != zaehlpunkt:
            logger.debug("Returned data: %s", data)
            raise SmartmeterQueryError("Returned data does not match given zaehlpunkt!")

        # Validate and extract valid OBIS data
        zaehlwerke = data.get("zaehlwerke")
        if not zaehlwerke:
            logger.debug("Returned data: %s", data)
            raise SmartmeterQueryError("Returned data does not contain any zaehlwerke or is empty.")

        valid_obis_data = self.find_valid_obis_data(zaehlwerke)
        return valid_obis_data

    def bewegungsdaten(
        self,
        zaehlpunktnummer: str = None,
        date_from: date = None,
        date_until: date = None,
        valuetype: const.ValueType = const.ValueType.QUARTER_HOUR,
        aggregat: str = None,
    ):
        """
        Query historical data in a batch
        If no arguments are given, a span of three year is queried (same day as today but from current year - 3).
        If date_from is not given but date_until, again a three year span is assumed.
        """
        customer_id, zaehlpunkt, anlagetype = self.get_zaehlpunkt(zaehlpunktnummer)

        if anlagetype == const.AnlagenType.FEEDING:
            if valuetype == const.ValueType.DAY:
                rolle = const.RoleType.DAILY_FEEDING.value
            else:
                rolle = const.RoleType.QUARTER_HOURLY_FEEDING.value
        else:
            if valuetype == const.ValueType.DAY:
                rolle = const.RoleType.DAILY_CONSUMING.value
            else:
                rolle = const.RoleType.QUARTER_HOURLY_CONSUMING.value

        if date_until is None:
            date_until = date.today()

        if date_from is None:
            date_from = date_until - relativedelta(years=3)

        query = {
            "geschaeftspartner": customer_id,
            "zaehlpunktnummer": zaehlpunkt,
            "rolle": rolle,
            "zeitpunktVon": date_from.strftime("%Y-%m-%dT%H:%M:00.000Z"), # we catch up from the exact date of the last import to compensate for time shift
            "zeitpunktBis": date_until.strftime("%Y-%m-%dT23:59:59.999Z"),
            "aggregat": aggregat or "NONE"
        }

        extra = {
            # For this API Call, requesting json is important!
            "Accept": "application/json"
        }

        data = self._call_api(
            f"user/messwerte/bewegungsdaten",
            base_url=const.API_URL_ALT,
            query=query,
            extra_headers=extra,
        )
        if data["descriptor"]["zaehlpunktnummer"] != zaehlpunkt:
            raise SmartmeterQueryError("Returned data does not match given zaehlpunkt!")
        return data
