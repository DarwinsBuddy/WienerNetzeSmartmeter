class SmartmeterError(Exception):
    def __init__(self, msg, code=None, error_response=""):
        self.code = code or 0
        self.error_response = error_response
        super().__init__(msg)

    @property
    def msg(self):
        return self.args[0]


class SmartmeterLoginError(SmartmeterError):
    pass


class SmartmeterConnectionError(SmartmeterError):
    pass


class SmartmeterQueryError(SmartmeterError):
    pass
