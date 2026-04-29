"""Smartmeter-specific exception types."""

class SmartmeterError(Exception):
    """Generic base error raised by the Smartmeter client."""

    def __init__(self, msg, code=None, error_response=""):
        """Create a Smartmeter error with message, code and raw response."""
        self.code = code or 0
        self.error_response = error_response
        super().__init__(msg)

    @property
    def msg(self):
        """Return the original error message."""
        return self.args[0]


class SmartmeterLoginError(SmartmeterError):
    """Raised when login fails."""

    pass


class SmartmeterConnectionError(SmartmeterError):
    """Raised due to connectivity or session issues."""

    pass


class SmartmeterQueryError(SmartmeterError):
    """Raised when the API returns unexpected query results."""

    pass
