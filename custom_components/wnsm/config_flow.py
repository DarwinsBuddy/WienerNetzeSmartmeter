"""Setting up the config flow for Home Assistant."""

import logging
from typing import Any, Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

from .api import Smartmeter
from .const import ATTRS_ZAEHLPUNKTE_CALL, DOMAIN, CONF_ZAEHLPUNKTE
from .utils import translate_dict

_LOGGER = logging.getLogger(__name__)

AUTH_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): cv.string, vol.Required(CONF_PASSWORD): cv.string}
)


class WienerNetzeSmartMeterCustomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Wiener Netze Smartmeter config flow."""

    data: Optional[dict[str, Any]]

    async def validate_auth(self, username: str, password: str) -> list[dict]:
        """Validate credentials and return the available metering points."""
        smartmeter = Smartmeter(username, password)
        await self.hass.async_add_executor_job(smartmeter.login)
        contracts = await self.hass.async_add_executor_job(smartmeter.zaehlpunkte)
        zaehlpunkte=[]
        if contracts is not None and isinstance(contracts, list) and len(contracts) > 0:
            for contract in contracts:
                if "zaehlpunkte" in contract:
                    zaehlpunkte.extend(contract["zaehlpunkte"])
        return zaehlpunkte


    async def async_step_user(self, user_input: Optional[dict[str, Any]] = None):
        """Handle a flow started by the user in the UI."""
        errors: dict[str, str] = {}
        zps = []
        if user_input is not None:
            try:
                zps = await self.validate_auth(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except Exception as exception:
                _LOGGER.error("Error validating Wiener Netze auth")
                _LOGGER.exception(exception)
                errors["base"] = "auth"
            if not errors:
                # Input is valid, set data.
                self.data = user_input
                self.data[CONF_ZAEHLPUNKTE] = [
                    translate_dict(zp, ATTRS_ZAEHLPUNKTE_CALL) for zp in zps
                    # Only create active Zaehlpunkte, because inactive ones can
                    # still appear in older contracts returned by the portal.
                    if zp["isActive"]
                ]

                # User is done authenticating, create the config entry.
                return self.async_create_entry(
                    title="Wiener Netze Smartmeter", data=self.data
                )

        return self.async_show_form(
            step_id="user", data_schema=AUTH_SCHEMA, errors=errors
        )
