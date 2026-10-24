"""Python wrappers for the Wiener Netze Smart Meter APIs.

This package exposes two client implementations:

``Smartmeter``
    Legacy client talking to the private portal API. Relies on
    HTML-scraping the Keycloak login flow.

``OfficialSmartmeter``
    Client for the public OAuth2 ``WN_SMART_METER_API`` gateway. Requires
    a client_id / client_secret / x-Gateway-APIKey tuple issued by
    Wiener Netze.
"""
from importlib.metadata import version

from .client import Smartmeter
from .official_client import OfficialSmartmeter

try:
    __version__ = version(__name__)
except Exception:  # pylint: disable=broad-except
    pass

__all__ = ["Smartmeter", "OfficialSmartmeter"]
