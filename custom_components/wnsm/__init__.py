"""Set up the Wiener Netze SmartMeter Integration component."""

from dataclasses import dataclass

from homeassistant import config_entries, core
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME

from .AsyncSmartmeter import AsyncSmartmeter
from .api import Smartmeter
from .const import (
    CONF_ENABLE_DAY_STATISTICS_IMPORT,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)


@dataclass(slots=True)
class WnsmRuntimeData:
    """Runtime data cached per config entry."""

    config: dict
    smartmeter: Smartmeter
    async_smartmeter: AsyncSmartmeter


async def async_setup_entry(
    hass: core.HomeAssistant,
    entry: config_entries.ConfigEntry,
) -> bool:
    """Set up platform from a ConfigEntry."""
    config = {**entry.data, **entry.options}
    config.setdefault(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
    config.setdefault(CONF_ENABLE_DAY_STATISTICS_IMPORT, True)

    smartmeter = Smartmeter(
        username=config[CONF_USERNAME],
        password=config[CONF_PASSWORD],
    )
    async_smartmeter = AsyncSmartmeter(hass, smartmeter)

    entry.runtime_data = WnsmRuntimeData(
        config=config,
        smartmeter=smartmeter,
        async_smartmeter=async_smartmeter,
    )

    # Compatibility cache for existing platform setup code paths.
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = config

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True


async def async_unload_entry(
    hass: core.HomeAssistant,
    entry: config_entries.ConfigEntry,
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        runtime_data = entry.runtime_data
        if runtime_data is not None and hasattr(runtime_data, "smartmeter"):
            runtime_data.smartmeter.session.close()
        entry.runtime_data = None
    return unload_ok


async def async_reload_entry(
    hass: core.HomeAssistant,
    entry: config_entries.ConfigEntry,
) -> None:
    """Reload config entry when options are updated from UI."""
    await hass.config_entries.async_reload(entry.entry_id)
