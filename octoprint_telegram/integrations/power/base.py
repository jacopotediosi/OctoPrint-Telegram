from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.context import PluginContext


class PowerPlugin(ABC):
    """A third-party plugin through which power outlets can be switched on and off."""

    def __init__(self, plugin_context: PluginContext):
        self.plugin_context = plugin_context
        self._logger = plugin_context.logger.getChild("PowerPlugin")

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """The identifier the plugin is registered under in OctoPrint."""

    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """The plugin name shown to users."""

    @abstractmethod
    def get_plugs_data(self) -> list[dict]:
        """
        Retrieve information about all plugs managed by this plugin.

        Returns:
            List[Dict[str, Any]]: A list of plug dictionaries, each containing:
                - "label" (str): Human-readable plug name for display purposes.
                - "is_on" (bool): Current power state of the plug (True if on, False if off).
                - "data" (str): Unique identifier used to identify the plug in plugin API calls.
        """

    @abstractmethod
    def turn_on(self, plug_data) -> None:
        """Switch a plug on."""

    @abstractmethod
    def turn_off(self, plug_data) -> None:
        """Switch a plug off."""
