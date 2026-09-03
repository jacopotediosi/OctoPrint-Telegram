from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from .hooks import ImageHookMethod, ImageHooks
from .snapshots import Snapshots
from .video import FfmpegPreset, Video
from .webcams import WebcamProfile, Webcams

if TYPE_CHECKING:
    import logging

    from octoprint.events import EventManager
    from octoprint.plugin.core import PluginManager
    from octoprint.printer import PrinterInterface

    from ..core.settings import OctoPrintSettings, Settings
    from ..integrations.plugins import Plugins


class Media:
    """Pictures and videos taken from the webcams."""

    def __init__(
        self,
        settings: Settings,
        octoprint_settings: OctoPrintSettings,
        plugins: Plugins,
        plugin_manager: PluginManager,
        printer: PrinterInterface,
        event_manager: EventManager,
        data_folder: str,
        logger: logging.Logger,
    ) -> None:
        """Set up the taking of pictures and videos from the webcams.

        Args:
            settings (Settings): The plugin settings.
            octoprint_settings (OctoPrintSettings): The settings stored by OctoPrint itself.
            plugins (Plugins): The OctoPrint plugins installed.
            plugin_manager (PluginManager): The OctoPrint plugin manager.
            printer (PrinterInterface): The printer.
            event_manager (EventManager): The OctoPrint event bus.
            data_folder (str): The plugin's data folder.
            logger (logging.Logger): The logger to write to.
        """
        self.webcams = Webcams(plugin_manager, plugins, octoprint_settings, logger)
        self.snapshots = Snapshots(self.webcams, logger)
        self.video = Video(self.webcams, settings, octoprint_settings, logger)
        self.hooks = ImageHooks(settings, printer, event_manager, logger)
        self._data_folder = data_folder

    def clear_temporary_files(self) -> None:
        """Discard any video left over from a previous run."""
        # TODO: the tmpgif folder is no longer used, this only empties what older versions left in it.
        # Remove this in the future.
        shutil.rmtree(os.path.join(self._data_folder, "tmpgif"), ignore_errors=True)


__all__ = ["FfmpegPreset", "ImageHookMethod", "ImageHooks", "Media", "Snapshots", "Video", "WebcamProfile", "Webcams"]
