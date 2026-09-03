from __future__ import annotations

from typing import TYPE_CHECKING

from octoprint.access.permissions import Permissions

if TYPE_CHECKING:
    from octoprint.plugin.core import PluginManager


class Frontend:
    """The plugin's frontend, as a recipient of live updates."""

    def __init__(self, plugin_manager: PluginManager, plugin_identifier: str) -> None:
        """Set up the channel the frontend live updates are pushed through.

        Args:
            plugin_manager (PluginManager): The OctoPrint plugin manager.
            plugin_identifier (str): The identifier the messages are sent under.
        """
        self._plugin_manager = plugin_manager
        self._plugin_identifier = plugin_identifier

    def update_known_chats(self, chats: dict) -> None:
        """Update the given chats in the known chats table."""
        self._plugin_manager.send_plugin_message(
            self._plugin_identifier,
            {"type": "update_known_chats", "chats": chats},
            permissions=[Permissions.SETTINGS],
        )

    def update_enrollment_countdown(self, remaining_seconds: int) -> None:
        """Update how long new chats may be enrolled."""
        self._plugin_manager.send_plugin_message(
            self._plugin_identifier,
            {"type": "enrollment_countdown", "remaining": remaining_seconds},
            permissions=[Permissions.SETTINGS],
        )
