from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from octoprint.plugin.core import PluginManager


class PluginStatus(Enum):
    """The availability of a plugin."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    NOT_INSTALLED = "not_installed"


class Plugins:
    """The OctoPrint plugins installed."""

    def __init__(self, plugin_manager: PluginManager):
        self._plugin_manager = plugin_manager

    def is_enabled(self, plugin_id: str) -> bool:
        """Whether a plugin is installed and enabled."""
        return bool(self._plugin_manager.get_plugin(plugin_id, True))

    def module(self, plugin_id: str):
        """The Python module of a plugin, or None when the plugin is unavailable."""
        return self._plugin_manager.get_plugin(plugin_id, True)

    def implementation(self, plugin_id: str):
        """The running instance of a plugin."""
        return self._plugin_manager.plugins[plugin_id].implementation

    def status(self, plugin_id: str) -> PluginStatus:
        """Availability of a plugin."""
        info = self._plugin_manager.get_plugin_info(plugin_id, require_enabled=False)
        if info is None:
            return PluginStatus.NOT_INSTALLED
        if not info.enabled:
            return PluginStatus.DISABLED
        return PluginStatus.ENABLED
