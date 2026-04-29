"""Public API surface of the Wiener-Netze client package."""

from importlib.metadata import version

from .client import Smartmeter

try:
    __version__ = version(__name__)
except Exception:
    # The package version is optional when the integration is used directly
    # from a local folder instead of an installed Python package.
    pass

__all__ = ["Smartmeter"]
