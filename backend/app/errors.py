class AppError(Exception):
    """Only controlled, credential-free messages may cross the API boundary."""

    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(code)
        self.code = code
        self.message = message
        self.status = status
