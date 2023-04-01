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
        """
        self.username = username
        self.password = password
        self.session = requests.Session()
        self._access_token = None
        self._refresh_token = None
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
            raise SmartmeterConnectionError("Could not login with credentials") from exception

        logger.debug(f"LOGIN HEADERS: {result.headers}")

        if "Location" not in result.headers:
            raise SmartmeterLoginError("Login failed. Check username/password.")
        location = result.headers["Location"]

        parsed_url = parse.urlparse(location)

        fragment_dict = dict([x.split("=") for x in parsed_url.fragment.split("&") if len(x.split("=")) == 2])
        if 'code' in fragment_dict:
            code = fragment_dict['code']
        else:
            raise SmartmeterLoginError("Login failed. Could not extract 'code' from 'Location'")
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
        self._refresh_token = result.json()["refresh_token"] # TODO: use this to refresh the token of this session instead of re-login. may be nicer for the API
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
                    "Could not obtain API Key from scripts"
                ) from exception
            for match in const.API_GATEWAY_TOKEN_REGEX.findall(response.text):
                return match
        raise SmartmeterConnectionError(
            "Could not obtain API Key - no match"
        )

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
    ):
        if base_url is None:
            base_url = const.API_URL
        url = f"{base_url}{endpoint}"

        if query:
            url += ("?" if "?" not in endpoint else "&") + parse.urlencode(query)

        logger.debug(f"REQUEST: {url}")

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "X-Gateway-APIKey": self._api_gateway_token,
        }

        if data:
            logger.debug(f"DATA: {data}")
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

    def consumptions(self):
        """Returns response from 'consumptions' endpoint."""
        return self._call_api("zaehlpunkt/consumptions")

    def base_information(self):
        """Returns response from 'baseInformation' endpoint."""
        return self._call_api("zaehlpunkt/baseInformation")

    def meter_readings(self):
        """Returns response from 'meterReadings' endpoint."""
        return self._call_api("zaehlpunkt/meterReadings")

    def verbrauch_raw(
        self, date_from: datetime, date_to: datetime = None, zaehlpunkt=None
    ):
        """Returns energy usage.

        This can be used to query the daily consumption for a long period of time,
        for example several months or a week.

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

    def verbrauch(self, date_from: datetime, zaehlpunkt = None, resolution: const.Resolution = const.Resolution.HOUR):
        """Returns energy usage for 24h after date_to.

        Args:
            date_from (datetime.datetime): Starting date for energy usage request
            zaehlpunkt (str, optional): Id for desired smartmeter.
                If None check for first meter in user profile.
            resolution (const.Resolution, optinal): Specify either 1h or 15min resolution

        Returns:
            dict: JSON response of api call to
                'm/messdaten/zaehlpunkt/ZAEHLPUNKT/verbrauch'
        """
        if zaehlpunkt is None:
            zaehlpunkt = self._get_first_zaehlpunkt()
        endpoint = f"messdaten/zaehlpunkt/{zaehlpunkt}/verbrauch"
        query = const.build_verbrauchs_args(
            dateFrom = self._dt_string(date_from),
            dayViewResolution = resolution.value,
        )
        return self._call_api(endpoint, query=query)

    def tages_verbrauch(self, day: datetime, zaehlpunkt = None, resolution: const.Resolution = const.Resolution.QUARTER_HOUR):
        """Returns energy usage for the current day.


        Args:
            day (datetime.datetime): Day date for the request
            zaehlpunkt (str, optional): Id for desired smartmeter.
                If None, check for first meter in user profile.
            resolution (const.Resolution, optinal): Specify either 1h or 15min resolution

        Returns:
            dict: JSON response of api call to
                'messdaten/zaehlpunkt/ZAEHLPUNKT/verbrauch'
        """
        # FIXME: Actually, using 00:00:00.000 does not query the beginning of the day!
        # The problem is, that the time has to specified in UTC and during standard time,
        # UTC day starts at 23:00:00 and during summer time even on 22:00:00!
        return self.verbrauch(day.replace(hour=0, minute=0, second=0, microsecond=0), zaehlpunkt, resolution)

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
