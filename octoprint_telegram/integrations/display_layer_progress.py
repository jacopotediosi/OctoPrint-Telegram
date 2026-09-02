from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging

    from .octoprint_api import OctoPrintApi
    from .plugins import Plugins

PLUGIN_ID = "DisplayLayerProgress"


class DisplayLayerProgress:
    """The layer and height readings published by the DisplayLayerProgress plugin."""

    def __init__(self, plugins: Plugins, api: OctoPrintApi, logger: logging.Logger) -> None:
        """Set up the access to the DisplayLayerProgress readings.

        Args:
            plugins (Plugins): The OctoPrint plugins installed.
            api (OctoPrintApi): The OctoPrint HTTP API.
            logger (logging.Logger): The logger to write to.
        """
        self._plugins = plugins
        self._api = api
        self._logger = logger.getChild("DisplayLayerProgress")

    def get_layer_progress_values(self) -> dict | None:
        """The current readings, or None when the plugin is unavailable or fails to answer."""
        layer_progress_values = None

        try:
            if self._plugins.is_enabled(PLUGIN_ID):
                values_request = self._api.send_request(f"/plugin/{PLUGIN_ID}/values", timeout=5)
                layer_progress_values = values_request.json()
            else:
                self._logger.debug("DisplayLayerProgress plugin not installed or disabled")
        except Exception:
            self._logger.exception("Caught an exception in get_layer_progress_values")

        return layer_progress_values
