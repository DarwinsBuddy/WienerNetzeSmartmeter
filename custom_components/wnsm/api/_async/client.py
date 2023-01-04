"""Contains the Async Smartmeter API Client."""
import asyncio
import json
import logging
import socket
from datetime import datetime
from urllib import parse

import aiohttp
import async_timeout
from lxml import html

from .. import constants as const
from ..errors import SmartmeterLoginError

logger = logging.getLogger(__name__)

TIMEOUT = 20


class AsyncSmartmeter:
    """Async Smartmeter Client."""

    def __init__(self, username, password, session=None, timeout=TIMEOUT):
        """Access the Smart Meter API asynchronously.

        Args:
            username (str): Username used for API Login
            password (str): Password used for API Login
            session (aiohttp.ClientSession): An optional session object
            timeout (int): Timeout for all session calls. Defaults to TIMEOUT.
        """
        self._username = username
        self._password = password
        self._session = session or aiohttp.ClientSession()
        self._timeout = timeout
        self._access_token = None
        self._api_gateway_token = None

    async def _get_login_action(self):
        login_url = const.AUTH_URL + "auth?" + parse.urlencode(const.LOGIN_ARGS)
        async with self._session.get(login_url) as response:
            tree = html.fromstring(await response.text())
            return tree.xpath("(//form/@action)")[0]

    async def _get_auth_code(self):

        action = await self._get_login_action()

        async with self._session.request(
            "POST",
            action,
            data={"username": self._username, "password": self._password},
            allow_redirects=False,
        ) as resp:
            if "Location" not in resp.headers:
                raise SmartmeterLoginError(
                    "Authentication failed. Check user credentials."
                )
            auth_code = resp.headers["Location"].split("&code=", 1)[1]
            return auth_code

    async def _get_api_key(self, access_token):
        async with self._session.request(
            "GET", const.PAGE_URL, data={"Authorization": f"Bearer {access_token}"}
        ) as result:
            tree = html.fromstring(await result.text())
            scripts = tree.xpath("(//script/@src)")
            for script in scripts:
                async with self._session.request(
                    "GET", const.PAGE_URL + script
                ) as response:
                    if const.MAIN_SCRIPT_REGEX.match(script):
                        for match in const.API_GATEWAY_TOKEN_REGEX.findall(
                            await response.text()
                        ):
                            return match
        return None

    async def refresh_token(self):
        """Create a valid access token."""
        async with self._session.request(
            "POST",
            const.AUTH_URL + "token",
            data=const.build_access_token_args(code=await self._get_auth_code()),
        ) as response:
            if response.status != 200:
                raise SmartmeterLoginError(
                    "Authentication failed. Check user credentials."
                )
            self._access_token = json.loads(await response.text())["access_token"]
            self._api_gateway_token = await self._get_api_key(self._access_token)

        logger.debug("Successfully authenticated Smart Meter API")

    async def async_get_access_token(self):
        """Return a valid access token."""
        pass

    def _dt_string(self, dt):
        return dt.strftime(const.API_DATE_FORMAT)[:-3] + "Z"

    async def _get_first_zaehlpunkt(self):
        """Get first zaehlpunkt."""
        zaehlpunkte = await self.get_zaehlpunkte()
        return zaehlpunkte[0]["zaehlpunkte"][0]["zaehlpunktnummer"]

    async def get_zaehlpunkte(self):
        """Get zaehlpunkte for currently logged in user."""
        return await self._request("zaehlpunkte")

    async def get_verbrauch_raw(
        self,
        date_from,
        date_to=None,
        zaehlpunkt=None,
    ):
        """Get verbrauch_raw from the API."""
        if date_to is None:
            date_to = datetime.now()
        if zaehlpunkt is None:
            zaehlpunkt = await self._get_first_zaehlpunkt()
        endpoint = f"messdaten/zaehlpunkt/{zaehlpunkt}/verbrauchRaw"
        query = {
            "dateFrom": self._dt_string(date_from),
            "dateTo": self._dt_string(date_to),
            "granularity": "DAY",
        }
        return await self._request(endpoint, query=query)

    async def get_verbrauch(
        self,
        date_from,
        date_to=None,
        zaehlpunkt=None,
    ):
        """Get verbrauch_raw from the API."""
        if date_to is None:
            date_to = datetime.now()
        if zaehlpunkt is None:
            zaehlpunkt = await self._get_first_zaehlpunkt()
        endpoint = f"messdaten/zaehlpunkt/{zaehlpunkt}/verbrauch"
        query = const.build_verbrauchs_args(
            dateFrom=self._dt_string(date_from), dateTo=self._dt_string(date_to)
        )
        return await self._request(endpoint, query=query)

    async def tages_verbrauch(
        self,
        day: datetime,
        zaehlpunkt=None,
    ):
        """Get verbrauch_raw from the API."""
        if zaehlpunkt is None:
            zaehlpunkt = await self._get_first_zaehlpunkt()
        endpoint = f"messdaten/zaehlpunkt/{zaehlpunkt}/verbrauch"
        query = const.build_verbrauchs_args(
            dateFrom=self._dt_string(day.replace(hour=0, minute=0, second=0))
        )
        return await self._request(endpoint, query=query)

    async def profil(self):
        """Get profil of logged in user."""
        return await self._request("user/profile", const.API_URL_ALT)

    async def zaehlpunkte(self):
        """Returns zaehlpunkte for currently logged in user."""
        return await self._request("zaehlpunkte")

    async def welcome(self):
        """Returns response from 'welcome' endpoint."""
        return await self._request("zaehlpunkt/default/welcome")

    async def _request(
        self,
        endpoint,
        base_url=None,
        method="GET",
        data=None,
        query=None,
    ):
        """Send requests to the Smartmeter API."""
        if base_url is None:
            base_url = const.API_URL
        url = f"{base_url}{endpoint}"
        if query:
            separator = "?" if "?" not in endpoint else "&"
            url += separator + parse.urlencode(query)

        headers = {"Authorization": f"Bearer {self._access_token}"}
        if self._api_gateway_token is not None:
            headers.update({"X-Gateway-APIKey": self._api_gateway_token})

        try:
            async with async_timeout.timeout(self._timeout):
                response = await self._session.request(
                    method, url, headers=headers, json=data
                )
                if response.status == 401:
                    await self.refresh_token()
                    return await self._request(endpoint, base_url, method, data, query)
                return await response.json()

        except asyncio.TimeoutError as exception:
            logger.error("Timeout error fetching information from %s - %s", url, exception)
        except (KeyError, TypeError) as exception:
            logger.error("Error parsing information from %s - %s", url, exception)
        except (aiohttp.ClientError, socket.gaierror) as exception:
            logger.error("Error fetching information from %s - %s", url, exception)
        except Exception as exception:  # pylint: disable=broad-except
            logger.error("Something really wrong happened! - %s", exception)
