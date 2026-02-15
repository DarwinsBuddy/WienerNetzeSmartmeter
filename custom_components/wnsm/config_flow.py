"""Config flow for Wiener Netze Smartmeter."""

from __future__ import annotations

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME

from .api import Smartmeter
from .const import (
    ATTRS_ZAEHLPUNKTE_CALL,
    CONF_ENABLE_DAY_STATISTICS_IMPORT,
    CONF_ZAEHLPUNKTE,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from .utils import translate_dict

_LOGGER = logging.getLogger(__name__)


def _options_schema(scan_interval: int, enable_day_statistics_import: bool) -> vol.Schema:
    """Return schema for options flow.

    Uses plain voluptuous validators for broad HA-version compatibility.
    """
    return vol.Schema(
        {
            vol.Required(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=1440)
            ),
            vol.Required(
                CONF_ENABLE_DAY_STATISTICS_IMPORT,
                default=enable_day_statistics_import,
            ): cv.boolean,
        }
    )


def _user_schema() -> vol.Schema:
    """Return schema for initial setup."""
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME): cv.string,
            vol.Required(CONF_PASSWORD): cv.string,
            vol.Optional(
                CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL_MINUTES
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            vol.Optional(CONF_ENABLE_DAY_STATISTICS_IMPORT, default=True): cv.boolean,
        }
    )


class WienerNetzeSmartMeterCustomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Wiener Netze Smartmeter config flow."""

    VERSION = 1

    async def _validate_auth(self, username: str, password: str) -> list[dict[str, Any]]:
        """Validate credentials and return active points list."""
        smartmeter = Smartmeter(username, password)
        await self.hass.async_add_executor_job(smartmeter.login)
        contracts = await self.hass.async_add_executor_job(smartmeter.zaehlpunkte)

        zaehlpunkte: list[dict[str, Any]] = []
        if isinstance(contracts, list):
            for contract in contracts:
                if "zaehlpunkte" in contract:
                    zaehlpunkte.extend(contract["zaehlpunkte"])
        return zaehlpunkte

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle initial setup from UI."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                zaehlpunkte = await self._validate_auth(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Error validating Wiener Netze auth")
                errors["base"] = "auth"
            else:
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()

                data = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_ZAEHLPUNKTE: [
                        translate_dict(zp, ATTRS_ZAEHLPUNKTE_CALL)
                        for zp in zaehlpunkte
                        if zp.get("isActive")
                    ],
                    CONF_SCAN_INTERVAL: user_input.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
                    ),
                    CONF_ENABLE_DAY_STATISTICS_IMPORT: user_input.get(
                        CONF_ENABLE_DAY_STATISTICS_IMPORT, True
                    ),
                }
                return self.async_create_entry(title="Wiener Netze Smartmeter", data=data)

        return self.async_show_form(step_id="user", data_schema=_user_schema(), errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get options flow for this handler."""
        return WienerNetzeSmartMeterOptionsFlow(config_entry)


class WienerNetzeSmartMeterOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Wiener Netze Smartmeter."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_scan_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES),
        )
        current_day_stats_import = self._config_entry.options.get(
            CONF_ENABLE_DAY_STATISTICS_IMPORT,
            self._config_entry.data.get(CONF_ENABLE_DAY_STATISTICS_IMPORT, True),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(
                current_scan_interval,
                current_day_stats_import,
            ),
        )
