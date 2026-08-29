from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.context import PluginContext


class FilamentPlugin(ABC):
    """A third-party plugin through which filament spools can be browsed and selected."""

    def __init__(self, plugin_context: PluginContext) -> None:
        self.plugin_context = plugin_context

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """The identifier the plugin is registered under in OctoPrint."""

    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """The plugin name shown to users."""

    @abstractmethod
    def list_spool(self) -> dict[str, str]:
        """
        Retrieve a mapping of spool IDs to their human-readable descriptions.

        Returns:
            dict: A dictionary mapping spool IDs to their short descriptions.

                  Each description follows the format: "Name Material Color (Vendor) [Remaining g]"

        Example:
            >>> plugin.list_spool()
            {
                "1": "PLA+ Red (Prusament) [850g]",
                "2": "PETG Green (SUNLU) [150g]",
                "3": "TPU Black (eSUN) [450g]"
            }
        """

    @abstractmethod
    def get_spool_details_msg(self, spool_id: str) -> str:
        """
        Retrieve detailed information for a specific spool and format it as HTML message.

        Args:
            spool_id: The ID of the spool to retrieve details for.

        Returns:
            str: HTML-formatted string containing spool details like (depends on the specific plugin)
                ID, name, vendor, material, color, cost, density, diameter, weight information, etc.

        Example:
            >>> plugin.get_spool_details_msg(1)
            '<b>ID</b>: 1\\n'
            '<b>Name</b>: Spool1\\n'
            '<b>Vendor</b>: Sunlu\\n'
            '<b>Material</b>: ABS\\n\\n'
            '<b>Cost</b>: 20.0\\n'
            '<b>Density</b>: 1.25\\n'
            '<b>Diameter</b>: 1.75\\n\\n'
            '<b>Total weight</b>: 1000g\\n'
            '<b>Used</b>: 300g\\n'
            '<b>Remaining</b>: 700g (70%)\\n'
        """

    @abstractmethod
    def select_spool(self, tool_index: str, spool_id: str) -> None:
        """Assign a spool to a tool."""

    @abstractmethod
    def deselect_spool(self, tool_index: str) -> None:
        """Clear the spool assigned to a tool."""

    @abstractmethod
    def get_selected_spools(self) -> dict[int, str]:
        """
        Retrieve a mapping of tool numbers to their currently selected spool human-readable descriptions.

        Returns:
        dict: A dictionary mapping tool numbers to their short spool descriptions.

                Each description follows the format: "Name Material Color (Vendor) [Remaining g]"

        Example:
        >>> plugin.get_selected_spools()
        {
            0: "PLA+ Red (Prusament) [850g]",
            1: "PETG Green (SUNLU) [150g]",
            2: "TPU Black (eSUN) [450g]"
        }
        """
