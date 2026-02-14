"""Shared base sensor helpers for WNSM entities."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity

from .AsyncSmartmeter import AsyncSmartmeter
from .api import Smartmeter


class WNSMBaseSensor(SensorEntity):
    """Provide shared Smartmeter client handling for sensors."""

    def __init__(
        self,
        async_smartmeter: AsyncSmartmeter | None,
        username: str,
        password: str,
    ) -> None:
        super().__init__()
        self.username = username
        self.password = password
        self._async_smartmeter = async_smartmeter

    def _get_async_smartmeter(self) -> AsyncSmartmeter:
        """Return shared async smartmeter client, fallback to per-entity one."""
        if self._async_smartmeter is None:
            smartmeter = Smartmeter(username=self.username, password=self.password)
            self._async_smartmeter = AsyncSmartmeter(self.hass, smartmeter)
        return self._async_smartmeter
