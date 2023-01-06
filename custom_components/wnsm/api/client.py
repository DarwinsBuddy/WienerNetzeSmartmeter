"""Contains the Smartmeter API Client."""
import logging
from datetime import datetime
from urllib import parse

import requests
from lxml import html

from . import constants as const
from .errors import SmartmeterConnectionError
from .errors import SmartmeterLoginError

logger = logging.getLogger(__name__)


class Smartmeter:
    """Smartmeter client."""

    def __init__(self, username, password):
        """Access the Smartmeter API.

        Args:
            username (str): Username used for API Login.
            password (str): Username used for API Login.
            login (bool, optional): If _login() should be called. Defaults to True.
        """
        self.username = username
        self.password = password
        self.session = requests.Session()
        self._access_token = None
        self._api_gateway_token = None

    def login(self):
        """
        login with credentials specified in ctor
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
        try:
            result = self.session.post(
                action,
                data={
                    "username": self.username,
                    "password": self.password,
                },
                allow_redirects=False,
            )
        except Exception as exception:
            raise SmartmeterConnectionError("Could not load login page.") from exception

        if "Location" not in result.headers:
            raise SmartmeterLoginError("Login failed. Check username/password.")

        code = result.headers["Location"].split("&code=", 1)[1]
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

        self._access_token = result.json()["access_token"]
        self._api_gateway_token = self._get_api_key(self._access_token)

    def _get_api_key(self, token):
        headers = {"Authorization": f"Bearer {token}"}
        try:
            result = self.session.get(const.PAGE_URL, headers=headers)
        except Exception as exception:
            raise SmartmeterConnectionError("Could not obtain API key") from exception
        tree = html.fromstring(result.content)
        scripts = tree.xpath("(//script/@src)")
        for script in scripts:
            try:
                response = self.session.get(const.PAGE_URL + script)
            except Exception as exception:
                raise SmartmeterConnectionError(
                    "Could not obtain API key"
                ) from exception
            if const.MAIN_SCRIPT_REGEX.match(script):
                for match in const.API_GATEWAY_TOKEN_REGEX.findall(response.text):
                    return match
        return None

    def _dt_string(self, datetime_string):
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
    ):
        if base_url is None:
            base_url = const.API_URL
        url = f"{base_url}{endpoint}"

        if query:
            url += ("?" if "?" not in endpoint else "&") + parse.urlencode(query)

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "X-Gateway-APIKey": self._api_gateway_token,
        }

        if data:
            headers["Content-Type"] = "application/json"

        response = self.session.request(
            method, url, headers=headers, json=data, timeout=timeout
        )

        if return_response:
            return response

        return response.json()

    def _get_first_zaehlpunkt(self):
        return self.zaehlpunkte()[0]["zaehlpunkte"][0]["zaehlpunktnummer"]

    def zaehlpunkte(self):
        """Returns zaehlpunkte for currently logged in user."""
        return self._call_api("zaehlpunkte")

    def welcome(self):
        """Returns response from 'welcome' endpoint."""
        return self._call_api("zaehlpunkt/default/welcome")

    def verbrauch_raw(
        self, date_from: datetime, date_to: datetime = None, zaehlpunkt=None
    ):
        """Returns energy usage.

        Args:
            date_from (datetime): Start date for energy usage request
            date_to (datetime, optional): End date for energy usage request.
                Defaults to datetime.now().
            zaehlpunkt (str, optional): Id for desired smartmeter.
                If None check for first meter in user profile.

        Returns:
            dict: JSON response of api call to
                'messdaten/zaehlpunkt/ZAEHLPUNKT/verbrauchRaw'
        """
        if date_to is None:
            date_to = datetime.now()
        if zaehlpunkt is None:
            zaehlpunkt = self._get_first_zaehlpunkt()
        endpoint = f"messdaten/zaehlpunkt/{zaehlpunkt}/verbrauchRaw"
        query = {
            "dateFrom": self._dt_string(date_from),
            "dateTo": self._dt_string(date_to),
            "granularity": "DAY",
        }
        return self._call_api(endpoint, query=query)

    def verbrauch(self, date_from: datetime, date_to: datetime = None, zaehlpunkt=None):
        """Returns energy usage.

        Args:
            date_from (datetime.datetime): Starting date for energy usage request
            date_to (datetime.datetime, optional): Ending date for energy usage request.
                Defaults to datetime.datetime.now().
            zaehlpunkt (str, optional): Id for desired smartmeter.
                If None check for first meter in user profile.

        Returns:
            dict: JSON response of api call to
                'm/messdaten/zaehlpunkt/ZAEHLPUNKT/verbrauch'
        """
        if date_to is None:
            date_to = datetime.now()
        if zaehlpunkt is None:
            zaehlpunkt = self._get_first_zaehlpunkt()
        endpoint = f"messdaten/zaehlpunkt/{zaehlpunkt}/verbrauch"
        query = const.build_verbrauchs_args(
            dateFrom=self._dt_string(date_from), dateTo=self._dt_string(date_to)
        )
        return self._call_api(endpoint, query=query)

    def tages_verbrauch(self, day: datetime, zaehlpunkt=None):
        """Returns energy usage.

        Args:
            day (datetime.datetime): Day date for the request
            zaehlpunkt (str, optional): Id for desired smartmeter.
                If None check for first meter in user profile.

        Returns:
            dict: JSON response of api call to
                'messdaten/zaehlpunkt/ZAEHLPUNKT/verbrauch'
        """

        if zaehlpunkt is None:
            zaehlpunkt = self._get_first_zaehlpunkt()
        endpoint = f"messdaten/zaehlpunkt/{zaehlpunkt}/verbrauch"
        query = const.build_verbrauchs_args(
            dateFrom=self._dt_string(day.replace(hour=0, minute=0, second=0))
        )
        return self._call_api(endpoint, query=query)

    def profil(self):
        """Returns profil of logged in user.

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
            zaehlpunkt (str, optional): Id for desired smart meter.
                If is None check for first meter in user profile.

        Returns:
            dict: JSON response of api call to 'user/ereignisse'
        """
        if date_to is None:
            date_to = datetime.now()
        if zaehlpunkt is None:
            zaehlpunkt = self._get_first_zaehlpunkt()
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
                If None check for first meter in user profile
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
