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

    clients = hass.data.setdefault(CLIENTS_DATA, {})
    lock = hass.data.setdefault(CLIENTS_LOCK, asyncio.Lock())
    key = (username, password)

    async with lock:
        if key not in clients:
            smartmeter = Smartmeter(username=username, password=password)
            clients[key] = AsyncSmartmeter(hass, smartmeter)
        return clients[key]
