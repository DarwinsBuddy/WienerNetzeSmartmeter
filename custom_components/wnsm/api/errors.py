"""Smartmeter Errors."""
import logging

logger = logging.getLogger(__name__)


class SmartmeterError(Exception):
    """Generic Error for Smartmeter."""

    def __init__(self, msg, code=None, error_response=""):
        """Creates a Smartmeter error with msg, code and error_response."""
        self.code = code or 0
        self.error_response = error_response
        super().__init__(msg)

    @property
    def msg(self):
        """Return msg."""
        return self.args[0]


class SmartmeterLoginError(SmartmeterError):
    """Raised when login fails."""


class SmartmeterConnectionError(SmartmeterError):
    """Raised due to network connectivity-related issues."""
