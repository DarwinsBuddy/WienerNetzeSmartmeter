"""Shared AsyncSmartmeter instances keyed by credentials."""

import asyncio

from homeassistant.core import HomeAssistant

from .AsyncSmartmeter import AsyncSmartmeter
from .api import Smartmeter
from .const import DOMAIN

CLIENTS_DATA = f"{DOMAIN}_shared_clients"
CLIENTS_LOCK = f"{DOMAIN}_shared_clients_lock"


async def async_get_shared_async_smartmeter(
    hass: HomeAssistant,
    username: str,
    password: str,
) -> AsyncSmartmeter:
    """Return one shared client per account.

    This is a fork-specific extension. The upstream release created fresh
    Smartmeter/AsyncSmartmeter objects per entity update, which made parallel
    logins and overlapping requests much more likely once the integration was
    extended from one sensor to three sensors per Zaehlpunkt.
    """
    clients = hass.data.setdefault(CLIENTS_DATA, {})
    lock = hass.data.setdefault(CLIENTS_LOCK, asyncio.Lock())
    key = (username, password)

    async with lock:
        if key not in clients:
            # Reuse the same authenticated session for all sensors that belong
            # to the same Wiener-Netze account.
            smartmeter = Smartmeter(username=username, password=password)
            clients[key] = AsyncSmartmeter(hass, smartmeter)
        return clients[key]
