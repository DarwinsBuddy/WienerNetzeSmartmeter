"""
Setting up config flow for homeassistant
"""
import logging
from typing import Any, Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.selector import NumberSelector, NumberSelectorConfig, NumberSelectorMode

from .api import Smartmeter
from .const import (
    ATTRS_ZAEHLPUNKTE_CALL,
    CONF_FEED_IN_PRICE_PER_KWH,
    CONF_PRICE_PER_KWH,
    CONF_ZAEHLPUNKTE,
    DOMAIN,
)
from .utils import translate_dict

_LOGGER = logging.getLogger(__name__)

AUTH_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): cv.string, vol.Required(CONF_PASSWORD): cv.string}
)

PRICE_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, step="any", unit_of_measurement="EUR/kWh", mode=NumberSelectorMode.BOX)
)


class WienerNetzeSmartMeterCustomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Wiener Netze Smartmeter config flow"""

    data: Optional[dict[str, Any]]

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return WienerNetzeSmartMeterOptionsFlow()

    async def validate_auth(self, username: str, password: str) -> list[dict]:
        """
        Validates credentials for smartmeter.
        Raises a ValueError if the auth credentials are invalid.
        """
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
        """Invoked when a user initiates a flow via the user interface."""
        errors: dict[str, str] = {}
        zps = []
        if user_input is not None:
            try:
                zps = await self.validate_auth(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except Exception as exception:  # pylint: disable=broad-except
                _LOGGER.error("Error validating Wiener Netze auth")
                _LOGGER.exception(exception)
                errors["base"] = "auth"
            if not errors:
                # Input is valid, set data
                self.data = user_input
                self.data[CONF_ZAEHLPUNKTE] = [
                    translate_dict(zp, ATTRS_ZAEHLPUNKTE_CALL) for zp in zps
                    if zp["isActive"] # only create active zaehlpunkte, as inactive ones can appear in old contracts
                ]
                # User is done authenticating, create entry
                return self.async_create_entry(
                    title="Wiener Netze Smartmeter", data=self.data
                )

        return self.async_show_form(
            step_id="user", data_schema=AUTH_SCHEMA, errors=errors
        )


class WienerNetzeSmartMeterOptionsFlow(config_entries.OptionsFlow):
    """Prices for the optional cost and compensation statistics, an empty field disables the statistic"""

    async def async_step_init(self, user_input: Optional[dict[str, Any]] = None) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PRICE_PER_KWH, description={"suggested_value": options.get(CONF_PRICE_PER_KWH)}
                ): PRICE_SELECTOR,
                vol.Optional(
                    CONF_FEED_IN_PRICE_PER_KWH, description={"suggested_value": options.get(CONF_FEED_IN_PRICE_PER_KWH)}
                ): PRICE_SELECTOR,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
