"""
Setting up config flow for homeassistant
"""
import logging
from typing import Any, Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

from .api import OfficialSmartmeter, Smartmeter
from .api import adapter as official_adapter
from .const import (
    ATTRS_ZAEHLPUNKTE_CALL,
    AUTH_METHOD_LEGACY,
    AUTH_METHOD_OFFICIAL,
    CONF_API_KEY,
    CONF_AUTH_METHOD,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_CUSTOMER_ID,
    CONF_SCOPE,
    CONF_WEB_PROFILE_ID,
    CONF_ZAEHLPUNKTE,
    DOMAIN,
)
from .utils import translate_dict

_LOGGER = logging.getLogger(__name__)

LEGACY_AUTH_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): cv.string, vol.Required(CONF_PASSWORD): cv.string}
)

OFFICIAL_AUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): cv.string,
        vol.Required(CONF_CLIENT_SECRET): cv.string,
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(CONF_WEB_PROFILE_ID): cv.string,
        vol.Optional(CONF_CUSTOMER_ID): cv.string,
        # Optional scope — omit unless Wiener Netze explicitly told you
        # the app was provisioned with one. See issue #276.
        vol.Optional(CONF_SCOPE): cv.string,
    }
)


class WienerNetzeSmartMeterCustomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Wiener Netze Smartmeter config flow.

    The first step is a menu that lets the user choose between the legacy
    username/password scraper and the new OAuth2-based official API. Each
    branch collects the appropriate credentials, validates them by
    performing one live ``zaehlpunkte`` call, then creates the entry.
    """

    VERSION = 1

    data: Optional[dict[str, Any]]

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------
    async def validate_auth(self, username: str, password: str) -> list[dict]:
        """Validate legacy credentials and return the list of zaehlpunkte."""
        smartmeter = Smartmeter(username, password)
        await self.hass.async_add_executor_job(smartmeter.login)
        contracts = await self.hass.async_add_executor_job(smartmeter.zaehlpunkte)
        zaehlpunkte = []
        if contracts is not None and isinstance(contracts, list) and len(contracts) > 0:
            for contract in contracts:
                if "zaehlpunkte" in contract:
                    zaehlpunkte.extend(contract["zaehlpunkte"])
        return zaehlpunkte

    async def validate_official_auth(
        self,
        client_id: str,
        client_secret: str,
        api_key: str,
        web_profile_id: Optional[str],
        customer_id: Optional[str],
        scope: Optional[str] = None,
    ) -> list[dict]:
        """Validate official API credentials and return legacy-shaped zaehlpunkte."""
        client = OfficialSmartmeter(
            client_id=client_id,
            client_secret=client_secret,
            api_key=api_key,
            web_profile_id=web_profile_id or None,
            scope=scope or None,
        )
        await self.hass.async_add_executor_job(client.login)
        raw = await self.hass.async_add_executor_job(client.zaehlpunkte)
        return official_adapter.zaehlpunkte_to_internal(
            raw,
            customer_id=customer_id or None,
        )

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------
    async def async_step_user(self, user_input: Optional[dict[str, Any]] = None):
        """Top-level entry point — show the auth-method picker."""
        return self.async_show_menu(
            step_id="user",
            menu_options={
                AUTH_METHOD_OFFICIAL: "Official API (OAuth2)",
                AUTH_METHOD_LEGACY: "Username & Password (legacy)",
            },
        )

    async def async_step_legacy(
        self, user_input: Optional[dict[str, Any]] = None
    ):
        """Username/password branch (legacy scraper)."""
        errors: dict[str, str] = {}
        zps: list[dict] = []
        if user_input is not None:
            try:
                zps = await self.validate_auth(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except Exception as exception:  # pylint: disable=broad-except
                _LOGGER.error("Error validating Wiener Netze legacy auth")
                _LOGGER.exception(exception)
                errors["base"] = "auth"
            if not errors:
                self.data = dict(user_input)
                self.data[CONF_AUTH_METHOD] = AUTH_METHOD_LEGACY
                self.data[CONF_ZAEHLPUNKTE] = [
                    translate_dict(zp, ATTRS_ZAEHLPUNKTE_CALL)
                    for zp in zps
                    # only create active zaehlpunkte, as inactive ones
                    # can appear in old contracts
                    if zp.get("isActive")
                ]
                return self.async_create_entry(
                    title="Wiener Netze Smartmeter", data=self.data
                )

        return self.async_show_form(
            step_id="legacy", data_schema=LEGACY_AUTH_SCHEMA, errors=errors
        )

    async def async_step_official(
        self, user_input: Optional[dict[str, Any]] = None
    ):
        """Official OAuth2 API branch."""
        errors: dict[str, str] = {}
        zps: list[dict] = []
        if user_input is not None:
            try:
                zps = await self.validate_official_auth(
                    client_id=user_input[CONF_CLIENT_ID],
                    client_secret=user_input[CONF_CLIENT_SECRET],
                    api_key=user_input[CONF_API_KEY],
                    web_profile_id=user_input.get(CONF_WEB_PROFILE_ID),
                    customer_id=user_input.get(CONF_CUSTOMER_ID),
                    scope=user_input.get(CONF_SCOPE),
                )
            except Exception as exception:  # pylint: disable=broad-except
                _LOGGER.error("Error validating Wiener Netze official API auth")
                _LOGGER.exception(exception)
                errors["base"] = "auth"
            if not errors:
                self.data = dict(user_input)
                self.data[CONF_AUTH_METHOD] = AUTH_METHOD_OFFICIAL
                self.data[CONF_ZAEHLPUNKTE] = [
                    translate_dict(zp, ATTRS_ZAEHLPUNKTE_CALL)
                    for zp in zps
                    if zp.get("isActive", True)
                ]
                return self.async_create_entry(
                    title="Wiener Netze Smartmeter (Official API)",
                    data=self.data,
                )

        return self.async_show_form(
            step_id="official", data_schema=OFFICIAL_AUTH_SCHEMA, errors=errors
        )
