from importlib.metadata import version

from .client import Smartmeter

try:
    __version__ = version(__name__)
except Exception:
    pass

__all__ = ["Smartmeter"]
