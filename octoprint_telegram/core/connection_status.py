class ConnectionStatus:
    """How the connection to Telegram is doing, as shown on the settings page."""

    def __init__(self) -> None:
        self.message = "Disconnected."
        self.ok = False

    def set(self, message: str, ok: bool = False) -> None:
        self.message = message
        self.ok = ok
