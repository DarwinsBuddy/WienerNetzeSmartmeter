"""Contains the Smartmeter API Client."""
import logging
from datetime import datetime, timedelta, date
from urllib import parse

import requests
from lxml import html

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
            password (str): Username used for API Login.
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

    def load_login_page(self):
        """
        loads login page and extracts encoded login url
        """
        login_url = const.AUTH_URL + "auth?" + parse.urlencode(const.LOGIN_ARGS)
        try:
            result = self.session.get(login_url)
        except Exception as exception:
            raise SmartmeterConnectionError("Could not load login page") from exception
        if result.status_code != 200:
            raise SmartmeterConnectionError(
                f"Could not load login page. Error: {result.content}"
            )
        tree = html.fromstring(result.content)
        action = tree.xpath("(//form/@action)")[0]
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
                data=const.build_access_token_args(code=code),
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
        url = self.load_login_page()
        code = self.credentials_login(url)
        tokens = self.load_tokens(code)

        self._access_token = tokens["access_token"]
        # TODO: use this to refresh the token of this session instead of re-login. may be nicer for the API
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
        key_b2c = None
        key_b2b = None

        self._access_valid_or_raise()

        headers = {"Authorization": f"Bearer {token}"}
        try:
            result = self.session.get(const.PAGE_URL, headers=headers)
        except Exception as exception:
            raise SmartmeterConnectionError("Could not obtain API key") from exception
        tree = html.fromstring(result.content)
        scripts = tree.xpath("(//script/@src)")

        # sort the scripts in some order to find the keys faster
        # so far, the script was called main.XXXX.js
        scripts = sorted(scripts, key=lambda x: "main" not in x)

        for script in scripts:
            if key_b2c is not None and key_b2b is not None:
                break
            try:
                response = self.session.get(const.PAGE_URL + script)
            except Exception as exception:
                raise SmartmeterConnectionError(
                    "Could not obtain API Key from scripts"
                ) from exception
            key_b2c = const.API_GATEWAY_TOKEN_REGEX.search(response.text)
            key_b2b = const.API_GATEWAY_B2B_TOKEN_REGEX.search(response.text)
        if key_b2c is None or key_b2b is None:
            raise SmartmeterConnectionError("Could not obtain API Key - no match")
        return key_b2c.group(1), key_b2b.group(1)

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
        url = f"{base_url}{endpoint}"

        if query:
            url += ("?" if "?" not in endpoint else "&") + parse.urlencode(query)

        logger.debug("REQUEST: %s" % url)

        headers = {
            "Authorization": f"Bearer {self._access_token}",
        }

        # For API calls to B2C or B2B, we need to add the Gateway-APIKey:
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

        if return_response:
            return response

        return response.json()

    def _get_first_zaehlpunkt(self) -> (str, str):
        zps = self.zaehlpunkte()[0]
        customer_id = zps["geschaeftspartner"]
        zp = zps["zaehlpunkte"][0]["zaehlpunktnummer"]
        return customer_id, zp

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
            customer_id, zaehlpunkt = self._get_first_zaehlpunkt()
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
            customer_id, zaehlpunkt = self._get_first_zaehlpunkt()
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
            customer_id, zaehlpunkt = self._get_first_zaehlpunkt()
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

    def historical_data(
        self,
        zaehlpunkt: str = None,
        date_from: date = None,
        date_until: date = None,
        valuetype: const.ValueType = const.ValueType.QUARTER_HOUR,
    ):
        """
        Query historical data in a batch
        If no arguments are given, a span of three year is queried (same day as today but from current year - 3).
        If date_from is not given but date_until, again a three year span is assumed.
        """
        if zaehlpunkt is None:
            customer_id, zaehlpunkt = self._get_first_zaehlpunkt()

        if date_until is None:
            date_until = date.today()

        if date_from is None:
            date_from = date_until.replace(year=date_until.year - 3)

        query = {
            "zaehlpunkt": zaehlpunkt,
            "datumVon": date_from.strftime("%Y-%m-%d"),
            "datumBis": date_until.strftime("%Y-%m-%d"),
            "wertetyp": valuetype.value,
        }

        extra = {
            # For this API Call, requesting json is important!
            "Accept": "application/json"
        }

        data = self._call_api(
            "zaehlpunkte/messwerte",
            base_url=const.API_URL_B2B,
            query=query,
            extra_headers=extra,
        )

        # Some Sanity Checks...
        if len(data) != 1 or data[0]["zaehlpunkt"] != zaehlpunkt or len(data[0]["zaehlwerke"]) != 1:
            # TODO: Is it possible to have multiple zaehlwerke in one zaehlpunkt?
            # I guess so, otherwise it would not be a list...
            # Probably (my guess), we would see this on the OBIS Code.
            # The OBIS Code can code for channels, thus we would probably see that there.
            # Keep that in mind if for someone this fails.
            logger.debug("Returned data: %s" % data)
            raise SmartmeterQueryError("Returned data does not match given zaehlpunkt!")
        obis_code = data[0]["zaehlwerke"][0]["obisCode"]
        if obis_code[0] != "1":
            logger.warning(f"The OBIS code of the meter ({obis_code}) reports that this meter does not count electrical energy!")
        return data[0]["zaehlwerke"][0]
