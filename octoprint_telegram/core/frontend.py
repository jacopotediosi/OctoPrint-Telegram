class Frontend:
    """The plugin's settings page, as a recipient of live updates."""

    def __init__(self, plugin_manager, plugin_identifier: str):
        self._plugin_manager = plugin_manager
        self._plugin_identifier = plugin_identifier

    def update_known_chats(self, chats: dict) -> None:
        """Show the given chats in the known chats table."""
        self._plugin_manager.send_plugin_message(
            self._plugin_identifier, {"type": "update_known_chats", "chats": chats}
        )

    def update_enrollment_countdown(self, remaining_seconds: int) -> None:
        """Show how long new chats may still enrol themselves."""
        self._plugin_manager.send_plugin_message(
            self._plugin_identifier, {"type": "enrollment_countdown", "remaining": remaining_seconds}
        )
